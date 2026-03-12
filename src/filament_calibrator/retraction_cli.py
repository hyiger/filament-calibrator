"""Retraction calibration CLI and pipeline orchestration.

Generates a two-tower retraction test specimen, slices it with firmware
retraction enabled, and inserts ``M207 S<length>`` commands at each height
level so the user can inspect stringing between the towers to find the
optimal retraction distance.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

import gcode_lib as gl

from filament_calibrator.cli import (
    _KNOWN_TYPES,
    _UNSET,
    _apply_config,
    _explicit_keys,
    _patch_m862_nozzle_flags,
    _redact_config_for_debug,
    _resolve_output_dir,
    _validate_printer_temps,
)
from filament_calibrator.config import _find_config_path, load_config
from filament_calibrator.retraction_insert import (
    compute_retraction_levels,
    insert_retraction_commands,
)
from filament_calibrator.retraction_model import (
    BASE_HEIGHT,
    BASE_LENGTH,
    BASE_WIDTH,
    RetractionTowerConfig,
    generate_retraction_tower_stl,
)
from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_THUMBNAILS,
    slice_retraction_specimen,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_LEVELS: int = 50
"""Maximum number of retraction levels allowed."""


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Create the ``retraction-test`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="retraction-test",
        description=(
            "Generate a retraction calibration two-tower print.  "
            "Firmware retraction length (M207) is varied at each "
            "height level so the user can inspect stringing between "
            "the towers to find the optimal retraction distance."
        ),
    )

    # -- Retraction options --
    retract = parser.add_argument_group("retraction options")
    retract.add_argument(
        "--start-retraction", type=float, default=0.0,
        help="Starting retraction length in mm (default: 0.0).",
    )
    retract.add_argument(
        "--end-retraction", type=float, default=2.0,
        help="Ending retraction length in mm (default: 2.0).",
    )
    retract.add_argument(
        "--retraction-step", type=float, default=0.1,
        help="Retraction length increment per level in mm (default: 0.1).",
    )

    # -- Model options --
    model = parser.add_argument_group("model options")
    model.add_argument(
        "--level-height", type=float, default=1.0,
        help="Height per retraction level in mm (default: 1.0).",
    )
    model.add_argument(
        "--filament-type", type=str, default="PLA",
        help=(
            "Filament type for preset lookup.  Known types: "
            + ", ".join(_KNOWN_TYPES) + "."
        ),
    )

    # -- Nozzle options --
    nozzle = parser.add_argument_group("nozzle options")
    nozzle.add_argument(
        "--nozzle-size", type=float, default=0.4,
        help="Nozzle diameter in mm (default: 0.4).",
    )
    nozzle.add_argument(
        "--nozzle-high-flow", action="store_true", default=False,
        help="Nozzle is a high-flow variant (sets F flag in M862.1).",
    )
    nozzle.add_argument(
        "--nozzle-hardened", action="store_true", default=False,
        help="Nozzle is hardened/abrasive-resistant (sets A flag in M862.1).",
    )

    # -- Slicer options --
    slicer = parser.add_argument_group("slicer options")
    slicer.add_argument(
        "--layer-height", type=float, default=_UNSET,
        help="Slicer layer height in mm (default: nozzle × 0.5).",
    )
    slicer.add_argument(
        "--extrusion-width", type=float, default=_UNSET,
        help="Slicer extrusion width in mm (default: nozzle × 1.125).",
    )
    slicer.add_argument("--nozzle-temp", type=int, default=_UNSET)
    slicer.add_argument("--bed-temp", type=int, default=_UNSET)
    slicer.add_argument("--fan-speed", type=int, default=_UNSET)
    slicer.add_argument("--config-ini", type=str, default=None)
    slicer.add_argument("--prusaslicer-path", type=str, default=None)
    slicer.add_argument("--bed-center", type=str, default=None)
    slicer.add_argument(
        "--extra-slicer-args", type=str,
        nargs=argparse.REMAINDER, default=None,
        help="Additional PrusaSlicer CLI arguments (must be last).",
    )

    # -- Printer model --
    printer_group = parser.add_argument_group("printer model")
    printer_group.add_argument(
        "--printer", type=str, default="COREONE",
        help="Printer model (default: COREONE).",
    )

    # -- Printer / upload --
    upload = parser.add_argument_group("printer / upload")
    upload.add_argument("--printer-url", type=str, default=None)
    upload.add_argument("--api-key", type=str, default=None)
    upload.add_argument(
        "--no-upload", action="store_true", default=False,
        help="Skip uploading to the printer.",
    )
    upload.add_argument(
        "--print-after-upload", action="store_true", default=False,
    )

    # -- Config file --
    parser.add_argument("--config", type=str, default=None)

    # -- Output --
    output = parser.add_argument_group("output options")
    output.add_argument("--output-dir", type=str, default=None)
    output.add_argument(
        "--keep-files", action="store_true", default=False,
        help="Keep intermediate STL and raw G-code files.",
    )
    output.add_argument(
        "--ascii-gcode", action="store_true", default=False,
        help="Output text .gcode instead of binary .bgcode.",
    )

    # -- Verbosity --
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False,
    )

    return parser


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_retraction_args(
    start: float,
    end: float,
    step: float,
    level_height: float = 1.0,
) -> int:
    """Validate retraction arguments and return the number of levels.

    Calls :func:`sys.exit` on invalid input.
    """
    if start < 0:
        sys.exit(
            f"error: --start-retraction must be non-negative (got {start})"
        )
    if step <= 0:
        sys.exit(f"error: --retraction-step must be positive (got {step})")
    if level_height <= 0:
        sys.exit(
            f"error: --level-height must be positive (got {level_height})"
        )
    if end <= start:
        sys.exit(
            f"error: --end-retraction ({end}) must be greater than "
            f"--start-retraction ({start})"
        )
    spread = end - start
    remainder = spread % step
    if remainder > 1e-9 and (step - remainder) > 1e-9:
        sys.exit(
            f"error: retraction range {spread} is not evenly divisible "
            f"by --retraction-step {step}"
        )
    num_levels = round(spread / step) + 1
    if num_levels > MAX_LEVELS:
        sys.exit(
            f"error: computed {num_levels} levels exceeds maximum of "
            f"{MAX_LEVELS} (range {start}→{end}, step {step})"
        )
    return num_levels


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _resolve_common(args: argparse.Namespace) -> dict:
    """Resolve settings shared across the retraction pipeline."""
    num_levels = _validate_retraction_args(
        args.start_retraction, args.end_retraction,
        args.retraction_step, args.level_height,
    )

    resolved = gl.resolve_filament_preset(
        args.filament_type,
        nozzle_temp=(
            args.nozzle_temp if args.nozzle_temp is not _UNSET else None
        ),
        bed_temp=(
            args.bed_temp if args.bed_temp is not _UNSET else None
        ),
        fan_speed=(
            args.fan_speed if args.fan_speed is not _UNSET else None
        ),
    )
    nozzle_temp: int = resolved["nozzle_temp"]
    bed_temp: int = resolved["bed_temp"]
    fan_speed: int = resolved["fan_speed"]

    nozzle_size: float = args.nozzle_size
    layer_height: float = (
        args.layer_height if args.layer_height is not _UNSET
        else round(nozzle_size * 0.5, 2)
    )
    extrusion_width: float = (
        args.extrusion_width if args.extrusion_width is not _UNSET
        else round(nozzle_size * 1.125, 2)
    )

    printer_name: Optional[str] = None
    bed_shape: Optional[str] = None
    if args.printer is not None:
        try:
            printer_name = gl.resolve_printer(args.printer)
        except ValueError as exc:
            sys.exit(f"error: {exc}")
        if args.bed_center is None:
            args.bed_center = gl.compute_bed_center(printer_name)
        bed_shape = gl.compute_bed_shape(printer_name)

    _validate_printer_temps(printer_name, nozzle_temp, bed_temp)

    return {
        "num_levels": num_levels,
        "nozzle_temp": nozzle_temp,
        "bed_temp": bed_temp,
        "fan_speed": fan_speed,
        "nozzle_size": nozzle_size,
        "layer_height": layer_height,
        "extrusion_width": extrusion_width,
        "printer_name": printer_name,
        "bed_shape": bed_shape,
    }


def _render_gcode_templates(
    args: argparse.Namespace,
    printer_name: Optional[str],
    nozzle_size: float,
    nozzle_temp: int,
    bed_temp: int,
) -> tuple[Optional[str], Optional[str]]:
    """Render printer-specific start/end G-code if applicable."""
    if printer_name is None or args.config_ini is not None:
        return None, None

    filament_preset = gl.FILAMENT_PRESETS.get(args.filament_type.upper())
    use_cool_fan = True
    if filament_preset is not None and filament_preset.get("enclosure"):
        use_cool_fan = False

    total_z = (
        BASE_HEIGHT + args.level_height * _validate_retraction_args(
            args.start_retraction, args.end_retraction,
            args.retraction_step, args.level_height,
        )
    )

    start_gcode = gl.render_start_gcode(
        printer_name,
        nozzle_dia=nozzle_size,
        bed_temp=bed_temp,
        hotend_temp=nozzle_temp,
        bed_center=args.bed_center or DEFAULT_BED_CENTER,
        model_width=BASE_LENGTH,
        model_depth=BASE_WIDTH,
        cool_fan=use_cool_fan,
    )
    end_gcode = gl.render_end_gcode(
        printer_name,
        max_layer_z=total_z,
    )
    return start_gcode, end_gcode


def _debug_common(
    args: argparse.Namespace,
    common: dict,
    toml_config: Dict[str, object],
) -> None:
    """Print common debug information."""
    cfg_path = _find_config_path(args.config)
    if cfg_path is not None:
        print(f"[DEBUG] Config file: {cfg_path}")
        print(f"[DEBUG] Config values: {_redact_config_for_debug(toml_config)}")
    else:
        print("[DEBUG] No config file loaded")

    filament_key = args.filament_type.upper()
    preset = gl.FILAMENT_PRESETS.get(filament_key)
    if preset is not None:
        print(f"[DEBUG] Filament preset '{filament_key}' found")
    else:
        print(f"[DEBUG] Filament type '{filament_key}' not in presets, "
              "using fallback defaults")
    print(f"[DEBUG] Resolved: nozzle_temp={common['nozzle_temp']} "
          f"bed_temp={common['bed_temp']} fan_speed={common['fan_speed']}")
    print(f"[DEBUG] Nozzle: {common['nozzle_size']} mm → "
          f"layer_height={common['layer_height']} "
          f"extrusion_width={common['extrusion_width']}")
    if common["printer_name"] is not None:
        print(f"[DEBUG] Printer: {common['printer_name']} "
              f"(bed center: {args.bed_center})")


def _upload(args: argparse.Namespace, gcode_path: str) -> None:
    """Upload G-code if enabled, or print the save path."""
    if not args.no_upload:
        if args.verbose:
            print(f"[DEBUG] Upload target: {args.printer_url}")
            print(f"[DEBUG] Print after upload: {args.print_after_upload}")
        print(f"Uploading to {args.printer_url}")
        filename = gl.prusalink_upload(
            base_url=args.printer_url,
            api_key=args.api_key,
            gcode_path=gcode_path,
            print_after_upload=args.print_after_upload,
        )
        print(f"Uploaded as: {filename}")
        if args.print_after_upload:
            print("Print started.")
    else:
        print(f"G-code saved to: {gcode_path}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def _run_pipeline(
    args: argparse.Namespace,
    toml_config: Dict[str, object],
) -> None:
    """Execute the retraction calibration pipeline."""
    common = _resolve_common(args)
    num_levels = common["num_levels"]
    nozzle_temp = common["nozzle_temp"]
    bed_temp = common["bed_temp"]
    fan_speed = common["fan_speed"]
    nozzle_size = common["nozzle_size"]
    layer_height = common["layer_height"]
    extrusion_width = common["extrusion_width"]
    printer_name = common["printer_name"]
    bed_shape = common["bed_shape"]

    if args.verbose:
        _debug_common(args, common, toml_config)

    config = RetractionTowerConfig(
        num_levels=num_levels,
        level_height=args.level_height,
        filament_type=args.filament_type,
    )
    out_dir = _resolve_output_dir(args.output_dir, prefix="retraction-")

    if args.verbose:
        print(
            f"[DEBUG] Retraction tower: {num_levels} levels, "
            f"{args.start_retraction}→{args.end_retraction}, "
            f"step={args.retraction_step}"
        )
        print(f"[DEBUG] Output directory: {out_dir}")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"Retraction: {args.start_retraction}→{args.end_retraction} "
        f"(step {args.retraction_step})  "
        f"Temp: {nozzle_temp}°C  Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    suffix = gl.unique_suffix()
    safe_type = gl.safe_filename_part(config.filament_type)
    stl_name = (
        f"retraction_tower_{safe_type}"
        f"_{args.start_retraction}_{args.retraction_step}x{num_levels}"
        f"_{suffix}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    generate_retraction_tower_stl(config, stl_path)

    # --- Step 2: Slice ---
    gcode_ext = gl.gcode_ext(binary=not args.ascii_gcode)
    raw_gcode_path = str(
        out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}")
    )
    print(f"Slicing → {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    start_gcode, end_gcode = _render_gcode_templates(
        args, printer_name, nozzle_size, nozzle_temp, bed_temp,
    )
    if args.verbose and start_gcode is not None:
        print(f"[DEBUG] Rendered {printer_name} start/end G-code")

    result = slice_retraction_specimen(
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
        print(
            f"PrusaSlicer failed (exit {result.returncode}):",
            file=sys.stderr,
        )
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # --- Step 3: Insert retraction commands ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", gcode_ext))
    print(f"Inserting retraction commands → {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    gl.inject_thumbnails(
        gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose,
    )
    if printer_name is not None:
        gl.patch_slicer_metadata(
            gf, printer_name, nozzle_size, verbose=args.verbose,
        )
    levels = compute_retraction_levels(
        start_length=args.start_retraction,
        length_step=args.retraction_step,
        num_levels=num_levels,
        level_height=args.level_height,
        base_height=config.base_height,
    )
    if args.verbose:
        print("[DEBUG] Retraction levels:")
        for lv in levels:
            print(
                f"[DEBUG]   Z {lv.z_start:.1f}–{lv.z_end:.1f} mm → "
                f"{lv.retraction_length:.2f} mm"
            )

    gf.lines = insert_retraction_commands(gf.lines, levels)
    gf.lines = _patch_m862_nozzle_flags(
        gf.lines,
        nozzle_hardened=args.nozzle_hardened,
        nozzle_high_flow=args.nozzle_high_flow,
    )
    gl.save(gf, final_gcode_path)

    # Print retraction level lookup table.
    print("\nRetraction length by height:")
    for lv in levels:
        print(
            f"  Z {lv.z_start:5.1f} - {lv.z_end:5.1f} mm  "
            f"->  {lv.retraction_length:.2f} mm"
        )
    print(
        "\nInspect stringing between the towers at each height "
        "to find your optimal retraction length.\n"
    )

    # --- Clean up intermediate files ---
    if not args.keep_files:
        Path(stl_path).unlink(missing_ok=True)
        Path(raw_gcode_path).unlink(missing_ok=True)

    # --- Step 4: Upload ---
    _upload(args, final_gcode_path)

    print("Done.")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> None:
    """Execute the retraction calibration pipeline."""
    toml_config = load_config(args.config)
    _apply_config(
        args, toml_config,
        explicit_keys=getattr(args, "_explicit_keys", None),
    )

    # Fail fast: validate upload requirements.
    if not args.no_upload and (not args.printer_url or not args.api_key):
        print(
            "Error: --printer-url and --api-key are required for upload.",
            file=sys.stderr,
        )
        sys.exit(1)

    _run_pipeline(args, toml_config)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point: parse arguments and run the pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args._explicit_keys = _explicit_keys(parser, argv)
    run(args)
