"""Command-line interface for volumetric flow calibration.

Orchestrates: model generation → vase-mode slicing → feedrate insertion → upload.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import gcode_lib as gl

from filament_calibrator.cli import (
    _ARGPARSE_DEFAULTS,
    _KNOWN_TYPES,
    _UNSET,
    _apply_config,
    _gcode_ext,
    _resolve_output_dir,
)
from filament_calibrator.config import _find_config_path, load_config
from filament_calibrator.flow_insert import compute_flow_levels, insert_flow_rates
from filament_calibrator.flow_model import FlowSpecimenConfig, generate_flow_specimen_stl
from filament_calibrator.printer_gcode import (
    KNOWN_PRINTERS,
    compute_bed_center,
    compute_bed_shape,
    resolve_printer,
)
from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_THUMBNAILS,
    slice_flow_specimen,
)
from filament_calibrator.thumbnail import inject_thumbnails


# Maximum number of flow levels to prevent excessively tall prints.
MAX_LEVELS = 50


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        prog="volumetric-flow",
        description=(
            "Generate, slice, and upload a volumetric flow calibration specimen. "
            "The model is a serpentine wall printed in vase mode; print speed "
            "increases at each height level to test maximum volumetric flow."
        ),
    )

    # --- Flow options ---
    flow = p.add_argument_group("flow options")
    flow.add_argument(
        "--start-speed", type=float, required=True,
        help="Starting volumetric flow rate in mm³/s (lowest, bottom level).",
    )
    flow.add_argument(
        "--end-speed", type=float, required=True,
        help="Ending volumetric flow rate in mm³/s (highest, top level).",
    )
    flow.add_argument(
        "--step", type=float, required=True,
        help="Flow rate increment per level in mm³/s.",
    )

    # --- Model options ---
    type_names = ", ".join(_KNOWN_TYPES)
    model = p.add_argument_group("model options")
    model.add_argument(
        "--level-height", type=float, default=1.0,
        help="Height per flow level in mm. Default: 1.0",
    )
    model.add_argument(
        "--filament-type", type=str, default="PLA",
        help=(
            f"Filament type. Known presets ({type_names}) set defaults "
            "for --nozzle-temp, --bed-temp, and --fan-speed automatically. "
            "Custom names are accepted but require explicit temperatures. "
            "Default: PLA"
        ),
    )

    # --- Nozzle options ---
    nozzle = p.add_argument_group("nozzle options")
    nozzle.add_argument(
        "--nozzle-size", type=float, default=0.4,
        help=(
            "Nozzle diameter in mm. Sets defaults for "
            "--layer-height (nozzle × 0.5) and --extrusion-width "
            "(nozzle × 1.125) when they are not explicitly provided. "
            "Default: 0.4"
        ),
    )

    # --- Slicer options ---
    slicer = p.add_argument_group("slicer options")
    slicer.add_argument(
        "--layer-height", type=float, default=_UNSET,
        help=(
            "Slicer layer height in mm. Default: derived from "
            "--nozzle-size (nozzle × 0.5)."
        ),
    )
    slicer.add_argument(
        "--extrusion-width", type=float, default=_UNSET,
        help=(
            "Slicer extrusion width in mm. Default: derived from "
            "--nozzle-size (nozzle × 1.125)."
        ),
    )
    slicer.add_argument(
        "--bed-temp", type=int, default=_UNSET,
        help=(
            "Bed temperature in °C. Overrides the default from "
            "--filament-type preset."
        ),
    )
    slicer.add_argument(
        "--fan-speed", type=int, default=_UNSET,
        help=(
            "Fan speed 0–100%%. Overrides the default from "
            "--filament-type preset."
        ),
    )
    slicer.add_argument(
        "--nozzle-temp", type=int, default=_UNSET,
        help=(
            "Nozzle temperature in °C. Overrides the default from "
            "--filament-type preset."
        ),
    )
    slicer.add_argument(
        "--config-ini", type=str, default=None,
        help="PrusaSlicer .ini config file. If omitted, built-in vase-mode defaults are used.",
    )
    slicer.add_argument(
        "--prusaslicer-path", type=str, default=None,
        help="Explicit path to PrusaSlicer executable.",
    )
    slicer.add_argument(
        "--bed-center", type=str, default=None,
        help=(
            "Bed centre as X,Y in mm (e.g. 125,110). Default: 125,110 "
            "(Prusa MK-series)."
        ),
    )
    slicer.add_argument(
        "--extra-slicer-args", type=str, nargs=argparse.REMAINDER, default=None,
        help="Additional raw CLI arguments for PrusaSlicer (must be last).",
    )

    # --- Printer model ---
    printer_names = ", ".join(sorted(KNOWN_PRINTERS))
    p.add_argument(
        "--printer", type=str, default="COREONE",
        help=(
            f"Printer model for bed dimensions and metadata. "
            f"Available: {printer_names} (also accepts mk4 as alias for mk4s). "
            "Auto-sets --bed-center and bed shape from the printer's preset."
        ),
    )

    # --- Printer / upload options ---
    printer = p.add_argument_group("printer options")
    printer.add_argument(
        "--printer-url", type=str, default=None,
        help="PrusaLink printer URL (e.g. http://192.168.1.100).",
    )
    printer.add_argument(
        "--api-key", type=str, default=None,
        help="PrusaLink API key.",
    )
    printer.add_argument(
        "--no-upload", action="store_true", default=False,
        help="Skip uploading to the printer.",
    )
    printer.add_argument(
        "--print-after-upload", action="store_true", default=False,
        help="Start printing immediately after upload.",
    )

    # --- Config file ---
    p.add_argument(
        "--config", type=str, default=None, metavar="PATH",
        help=(
            "Path to a TOML config file. "
            "Default lookup: ./filament-calibrator.toml, "
            "then ~/.config/filament-calibrator/config.toml."
        ),
    )

    # --- Output options ---
    output = p.add_argument_group("output options")
    output.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory for output files. Default: temp directory.",
    )
    output.add_argument(
        "--keep-files", action="store_true", default=False,
        help="Keep intermediate files (STL, raw G-code).",
    )
    output.add_argument(
        "--ascii-gcode", action="store_true", default=False,
        help=(
            "Output ASCII (.gcode) instead of binary (.bgcode). "
            "Binary is the default; it supports thumbnail previews "
            "on the printer LCD."
        ),
    )

    # --- Verbosity ---
    p.add_argument(
        "-v", "--verbose", action="store_true", default=False,
        help="Show detailed debug output.",
    )

    return p


def _validate_flow_args(
    start_speed: float,
    end_speed: float,
    step: float,
) -> int:
    """Validate flow-rate arguments and return the number of levels.

    Calls :func:`sys.exit` on invalid input.
    """
    if start_speed <= 0:
        sys.exit(f"error: --start-speed must be positive (got {start_speed})")
    if step <= 0:
        sys.exit(f"error: --step must be positive (got {step})")
    if end_speed <= start_speed:
        sys.exit(
            f"error: --end-speed ({end_speed}) must be greater than "
            f"--start-speed ({start_speed})"
        )
    spread = end_speed - start_speed
    # Allow small floating-point tolerance when checking divisibility.
    remainder = spread % step
    if remainder > 1e-9 and (step - remainder) > 1e-9:
        sys.exit(
            f"error: flow range {spread} mm³/s is not evenly divisible "
            f"by --step {step}"
        )
    num_levels = round(spread / step) + 1
    if num_levels > MAX_LEVELS:
        sys.exit(
            f"error: computed {num_levels} levels exceeds maximum of "
            f"{MAX_LEVELS} (range {start_speed}→{end_speed} mm³/s, "
            f"step {step})"
        )
    return num_levels


def _resolve_preset(args: argparse.Namespace) -> Dict[str, object]:
    """Look up the filament preset and return resolved slicer settings.

    Returns a dict with keys ``nozzle_temp``, ``bed_temp``, ``fan_speed``.
    """
    filament_key = args.filament_type.upper()
    preset = gl.FILAMENT_PRESETS.get(filament_key)

    if preset is not None:
        default_nozzle = int(preset["hotend"])
        default_bed = int(preset["bed"])
        default_fan = int(preset["fan"])
    else:
        default_nozzle = 210
        default_bed = 60
        default_fan = 100

    return {
        "nozzle_temp": args.nozzle_temp if args.nozzle_temp is not _UNSET else default_nozzle,
        "bed_temp": args.bed_temp if args.bed_temp is not _UNSET else default_bed,
        "fan_speed": args.fan_speed if args.fan_speed is not _UNSET else default_fan,
    }


def run(args: argparse.Namespace) -> None:
    """Execute the full volumetric-flow calibration pipeline.

    1. Validate flow arguments.
    2. Generate the serpentine specimen STL.
    3. Slice in vase mode with PrusaSlicer.
    4. Insert feedrate overrides into the G-code.
    5. Upload to the printer (unless ``--no-upload``).
    """
    # Load TOML config and apply defaults.
    toml_config = load_config(args.config)
    _apply_config(args, toml_config)

    if args.verbose:
        cfg_path = _find_config_path(args.config)
        if cfg_path is not None:
            print(f"[DEBUG] Config file: {cfg_path}")
            print(f"[DEBUG] Config values: {toml_config}")
        else:
            print("[DEBUG] No config file loaded")

    # Fail fast: validate upload requirements.
    if not args.no_upload and (not args.printer_url or not args.api_key):
        print("Error: --printer-url and --api-key are required for upload.",
              file=sys.stderr)
        sys.exit(1)

    # Validate flow args and compute level count.
    num_levels = _validate_flow_args(
        args.start_speed, args.end_speed, args.step,
    )

    # Resolve filament preset for slicer settings.
    resolved = _resolve_preset(args)
    nozzle_temp: int = resolved["nozzle_temp"]
    bed_temp: int = resolved["bed_temp"]
    fan_speed: int = resolved["fan_speed"]

    # Resolve printer model for bed dimensions and metadata.
    printer_name: Optional[str] = None
    bed_shape: Optional[str] = None
    if args.printer is not None:
        printer_name = resolve_printer(args.printer)
        if args.bed_center is None:
            args.bed_center = compute_bed_center(printer_name)
        bed_shape = compute_bed_shape(printer_name)

    # Derive layer height and extrusion width from nozzle size.
    nozzle_size: float = args.nozzle_size
    layer_height: float = (
        args.layer_height if args.layer_height is not _UNSET
        else round(nozzle_size * 0.5, 2)
    )
    extrusion_width: float = (
        args.extrusion_width if args.extrusion_width is not _UNSET
        else round(nozzle_size * 1.125, 2)
    )

    if args.verbose:
        filament_key = args.filament_type.upper()
        preset = gl.FILAMENT_PRESETS.get(filament_key)
        if preset is not None:
            print(f"[DEBUG] Filament preset '{filament_key}' found")
        else:
            print(f"[DEBUG] Filament type '{filament_key}' not in presets, "
                  "using fallback defaults")
        print(f"[DEBUG] Resolved: nozzle_temp={nozzle_temp} bed_temp={bed_temp} "
              f"fan_speed={fan_speed}")
        print(f"[DEBUG] Nozzle: {nozzle_size} mm → "
              f"layer_height={layer_height} extrusion_width={extrusion_width}")
        if printer_name is not None:
            print(f"[DEBUG] Printer: {printer_name} "
                  f"(bed center: {args.bed_center})")

    config = FlowSpecimenConfig(
        num_levels=num_levels,
        level_height=args.level_height,
        filament_type=args.filament_type,
    )
    out_dir = _resolve_output_dir(args.output_dir)

    if args.verbose:
        print(f"[DEBUG] Flow: {num_levels} levels, "
              f"{args.start_speed}→{args.end_speed} mm³/s, "
              f"step={args.step} mm³/s")
        print(f"[DEBUG] Output directory: {out_dir}")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"Flow: {args.start_speed}→{args.end_speed} mm³/s  "
        f"Temp: {nozzle_temp}°C  Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    stl_name = (
        f"flow_specimen_{config.filament_type}"
        f"_{args.start_speed}_{args.step}x{num_levels}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    generate_flow_specimen_stl(config, stl_path)

    # --- Step 2: Slice in vase mode ---
    gcode_ext = _gcode_ext(args.ascii_gcode)
    raw_gcode_path = str(out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}"))
    print(f"Slicing (vase mode) → {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    result = slice_flow_specimen(
        stl_path=stl_path,
        output_gcode_path=raw_gcode_path,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        config_ini=args.config_ini,
        prusaslicer_path=args.prusaslicer_path,
        extra_args=args.extra_slicer_args,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        bed_center=args.bed_center,
        bed_shape=bed_shape,
        nozzle_diameter=nozzle_size,
        printer_model=printer_name,
        binary_gcode=not args.ascii_gcode,
    )
    if args.verbose:
        print(f"[DEBUG] PrusaSlicer command: {' '.join(result.cmd)}")
        if result.stdout.strip():
            print(f"[DEBUG] PrusaSlicer stdout: {result.stdout.strip()}")

    if not result.ok:
        print(f"PrusaSlicer failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # --- Step 3: Insert flow-rate feedrates ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", gcode_ext))
    print(f"Inserting flow rates → {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    inject_thumbnails(gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose)
    levels = compute_flow_levels(
        start_flow=args.start_speed,
        flow_step=args.step,
        num_levels=num_levels,
        level_height=args.level_height,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
    )
    if args.verbose:
        print("[DEBUG] Flow levels:")
        for lv in levels:
            print(f"[DEBUG]   Z {lv.z_start:.1f}–{lv.z_end:.1f} mm → "
                  f"{lv.flow_rate:.1f} mm³/s (F{lv.feedrate:.0f})")

    gf.lines = insert_flow_rates(gf.lines, levels)
    gl.save(gf, final_gcode_path)

    # --- Clean up intermediate files ---
    if not args.keep_files:
        Path(stl_path).unlink(missing_ok=True)
        Path(raw_gcode_path).unlink(missing_ok=True)

    # --- Step 4: Upload ---
    if not args.no_upload:
        if args.verbose:
            print(f"[DEBUG] Upload target: {args.printer_url}")
            print(f"[DEBUG] Print after upload: {args.print_after_upload}")
        print(f"Uploading to {args.printer_url}")
        filename = gl.prusalink_upload(
            base_url=args.printer_url,
            api_key=args.api_key,
            gcode_path=final_gcode_path,
            print_after_upload=args.print_after_upload,
        )
        print(f"Uploaded as: {filename}")
        if args.print_after_upload:
            print("Print started.")
    else:
        print(f"G-code saved to: {final_gcode_path}")

    print("Done.")


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point: parse arguments and run the pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)
    run(args)
