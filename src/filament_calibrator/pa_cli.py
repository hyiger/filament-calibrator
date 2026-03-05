"""Command-line interface for pressure advance calibration.

Orchestrates: model generation → slicing → PA command insertion → upload.
"""
from __future__ import annotations

import argparse
import sys
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
from filament_calibrator.pa_insert import compute_pa_levels, insert_pa_commands
from filament_calibrator.pa_model import (
    TOWER_DEPTH,
    TOWER_WIDTH,
    PATowerConfig,
    generate_pa_tower_stl,
)
from filament_calibrator.printer_gcode import (
    KNOWN_PRINTERS,
    compute_bed_center,
    compute_bed_shape,
    render_end_gcode,
    render_start_gcode,
    resolve_printer,
)
from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_THUMBNAILS,
    slice_pa_specimen,
)
from filament_calibrator.thumbnail import inject_thumbnails, patch_slicer_metadata


# Maximum number of PA levels to prevent excessively tall prints.
MAX_LEVELS = 50

# Valid firmware types for pressure advance commands.
FIRMWARE_CHOICES = ("marlin", "klipper")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        prog="pressure-advance",
        description=(
            "Generate, slice, and upload a pressure advance calibration tower. "
            "The model is a hollow rectangle with sharp corners; PA value "
            "increases at each height level to find optimal pressure advance."
        ),
    )

    # --- PA options ---
    pa = p.add_argument_group("pressure advance options")
    pa.add_argument(
        "--start-pa", type=float, required=True,
        help="Starting PA value (bottom level).",
    )
    pa.add_argument(
        "--end-pa", type=float, required=True,
        help="Ending PA value (top level).",
    )
    pa.add_argument(
        "--pa-step", type=float, required=True,
        help="PA value increment per level.",
    )
    pa.add_argument(
        "--firmware", type=str, default="marlin",
        choices=FIRMWARE_CHOICES,
        help=(
            "Firmware type for PA commands. "
            "'marlin' uses M900 K<value>, "
            "'klipper' uses SET_PRESSURE_ADVANCE ADVANCE=<value>. "
            "Default: marlin"
        ),
    )

    # --- Model options ---
    type_names = ", ".join(_KNOWN_TYPES)
    model = p.add_argument_group("model options")
    model.add_argument(
        "--level-height", type=float, default=1.0,
        help="Height per PA level in mm. Default: 1.0",
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
        help="PrusaSlicer .ini config file. If omitted, built-in defaults are used.",
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
            f"Printer model for start/end G-code. "
            f"Available: {printer_names} (also accepts mk4 as alias for mk4s). "
            "When set and no --config-ini is given, inserts printer-specific "
            "start/end G-code (homing, mesh bed leveling, purge line, parking). "
            "Also auto-sets --bed-center from the printer's bed dimensions."
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


def _validate_pa_args(
    start_pa: float,
    end_pa: float,
    pa_step: float,
) -> int:
    """Validate PA arguments and return the number of levels.

    Calls :func:`sys.exit` on invalid input.
    """
    if start_pa < 0:
        sys.exit(f"error: --start-pa must be non-negative (got {start_pa})")
    if pa_step <= 0:
        sys.exit(f"error: --pa-step must be positive (got {pa_step})")
    if end_pa <= start_pa:
        sys.exit(
            f"error: --end-pa ({end_pa}) must be greater than "
            f"--start-pa ({start_pa})"
        )
    spread = end_pa - start_pa
    # Allow small floating-point tolerance when checking divisibility.
    remainder = spread % pa_step
    if remainder > 1e-9 and (pa_step - remainder) > 1e-9:
        sys.exit(
            f"error: PA range {spread} is not evenly divisible "
            f"by --pa-step {pa_step}"
        )
    num_levels = round(spread / pa_step) + 1
    if num_levels > MAX_LEVELS:
        sys.exit(
            f"error: computed {num_levels} levels exceeds maximum of "
            f"{MAX_LEVELS} (range {start_pa}→{end_pa}, "
            f"step {pa_step})"
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
    """Execute the full pressure advance calibration pipeline.

    1. Validate PA arguments.
    2. Generate the hollow rectangular tower STL.
    3. Slice with PrusaSlicer.
    4. Insert PA commands into the G-code.
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

    # Validate PA args and compute level count.
    num_levels = _validate_pa_args(
        args.start_pa, args.end_pa, args.pa_step,
    )

    # Resolve filament preset for slicer settings.
    resolved = _resolve_preset(args)
    nozzle_temp: int = resolved["nozzle_temp"]
    bed_temp: int = resolved["bed_temp"]
    fan_speed: int = resolved["fan_speed"]

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

    # Resolve printer model for start/end G-code.
    printer_name: Optional[str] = None
    bed_shape: Optional[str] = None
    if args.printer is not None:
        printer_name = resolve_printer(args.printer)
        # Auto-set bed center and shape from printer presets if not explicit.
        if args.bed_center is None:
            args.bed_center = compute_bed_center(printer_name)
        bed_shape = compute_bed_shape(printer_name)

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

    config = PATowerConfig(
        num_levels=num_levels,
        level_height=args.level_height,
        filament_type=args.filament_type,
    )
    out_dir = _resolve_output_dir(args.output_dir)

    if args.verbose:
        print(f"[DEBUG] PA: {num_levels} levels, "
              f"{args.start_pa}→{args.end_pa}, "
              f"step={args.pa_step}")
        print(f"[DEBUG] Output directory: {out_dir}")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"PA: {args.start_pa}→{args.end_pa} (step {args.pa_step})  "
        f"Firmware: {args.firmware}  "
        f"Temp: {nozzle_temp}°C  Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    stl_name = (
        f"pa_tower_{config.filament_type}"
        f"_{args.start_pa}_{args.pa_step}x{num_levels}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    generate_pa_tower_stl(config, stl_path)

    # --- Step 2: Slice ---
    gcode_ext = _gcode_ext(args.ascii_gcode)
    raw_gcode_path = str(out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}"))
    print(f"Slicing → {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    # Render printer-specific start/end G-code when --printer is set
    # and no --config-ini is given (config.ini already has start/end gcode).
    start_gcode: Optional[str] = None
    end_gcode: Optional[str] = None
    if printer_name is not None and args.config_ini is None:
        total_height = num_levels * args.level_height
        # Determine whether to use cooling fan during MBL.
        filament_preset = gl.FILAMENT_PRESETS.get(
            args.filament_type.upper()
        )
        use_cool_fan = True
        if filament_preset is not None and filament_preset.get("enclosure"):
            use_cool_fan = False

        start_gcode = render_start_gcode(
            printer_name,
            nozzle_dia=nozzle_size,
            bed_temp=bed_temp,
            hotend_temp=nozzle_temp,
            bed_center=args.bed_center or DEFAULT_BED_CENTER,
            model_width=TOWER_WIDTH,
            model_depth=TOWER_DEPTH,
            cool_fan=use_cool_fan,
        )
        end_gcode = render_end_gcode(
            printer_name,
            max_layer_z=total_height,
        )
        if args.verbose:
            print(f"[DEBUG] Rendered {printer_name} start/end G-code")

    result = slice_pa_specimen(
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
        start_gcode=start_gcode,
        end_gcode=end_gcode,
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

    # --- Step 3: Insert PA commands ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", gcode_ext))
    print(f"Inserting PA commands → {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    inject_thumbnails(gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose)
    if printer_name is not None:
        patch_slicer_metadata(
            gf, printer_name, nozzle_size, verbose=args.verbose
        )
    levels = compute_pa_levels(
        start_pa=args.start_pa,
        pa_step=args.pa_step,
        num_levels=num_levels,
        level_height=args.level_height,
    )
    if args.verbose:
        print("[DEBUG] PA levels:")
        for lv in levels:
            print(f"[DEBUG]   Z {lv.z_start:.1f}–{lv.z_end:.1f} mm → "
                  f"PA {lv.pa_value:.4f}")

    gf.lines = insert_pa_commands(gf.lines, levels, firmware=args.firmware)
    gl.save(gf, final_gcode_path)

    # Print PA level lookup table for the user.
    print("\nPA value by height:")
    for lv in levels:
        print(f"  Z {lv.z_start:5.1f} - {lv.z_end:5.1f} mm  ->  PA {lv.pa_value:.4f}")
    print(f"\nMeasure the height with the sharpest corners to find your optimal PA value.\n")

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
