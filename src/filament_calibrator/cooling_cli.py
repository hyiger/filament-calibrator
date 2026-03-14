"""Cooling/fan-speed calibration CLI and pipeline orchestration.

Generates a single-tower cooling test specimen, slices it, and inserts
``M106 S<value>`` fan-speed commands at each height level so the user can
inspect print quality at each height to find the optimal fan speed.
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
    _print_estimate,
    add_common_args,
)
from filament_calibrator.config import _find_config_path, load_config
from filament_calibrator.cooling_insert import (
    compute_cooling_levels,
    insert_cooling_commands,
)
from filament_calibrator.cooling_model import (
    BASE_HEIGHT,
    BASE_LENGTH,
    BASE_WIDTH,
    CoolingTowerConfig,
    generate_cooling_tower_stl,
)
from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_THUMBNAILS,
    slice_cooling_specimen,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_LEVELS: int = 50
"""Maximum number of cooling levels allowed."""


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Create the ``cooling-test`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="cooling-test",
        description=(
            "Generate a cooling/fan-speed calibration tower print.  "
            "Fan speed (M106) is varied at each height level so the "
            "user can inspect print quality at each height to find "
            "the optimal fan speed."
        ),
    )

    cooling = parser.add_argument_group("cooling options")
    cooling.add_argument(
        "--start-fan", type=int, default=0,
        help="Starting fan speed percentage, 0-100 (default: 0).",
    )
    cooling.add_argument(
        "--end-fan", type=int, default=100,
        help="Ending fan speed percentage, 0-100 (default: 100).",
    )
    cooling.add_argument(
        "--fan-step", type=int, default=10,
        help="Fan speed percentage increment per level (default: 10).",
    )

    model = parser.add_argument_group("model options")
    model.add_argument(
        "--level-height", type=float, default=5.0,
        help="Height per cooling level in mm (default: 5.0).",
    )
    model.add_argument(
        "--filament-type", type=str, default="PLA",
        help=(
            "Filament type for preset lookup.  Known types: "
            + ", ".join(_KNOWN_TYPES) + "."
        ),
    )

    add_common_args(parser)
    return parser


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_cooling_args(
    start_fan: int,
    end_fan: int,
    fan_step: int,
    level_height: float = 5.0,
) -> int:
    """Validate cooling arguments and return the number of levels.

    Calls :func:`sys.exit` on invalid input.
    """
    if start_fan < 0:
        sys.exit(
            f"error: --start-fan must be non-negative (got {start_fan})"
        )
    if fan_step <= 0:
        sys.exit(f"error: --fan-step must be positive (got {fan_step})")
    if level_height <= 0:
        sys.exit(
            f"error: --level-height must be positive (got {level_height})"
        )
    if end_fan <= start_fan:
        sys.exit(
            f"error: --end-fan ({end_fan}) must be greater than "
            f"--start-fan ({start_fan})"
        )
    if end_fan > 100:
        sys.exit(
            f"error: --end-fan must be at most 100 (got {end_fan})"
        )
    spread = end_fan - start_fan
    remainder = spread % fan_step
    if remainder != 0:
        sys.exit(
            f"error: fan range {spread} is not evenly divisible "
            f"by --fan-step {fan_step}"
        )
    num_levels = spread // fan_step + 1
    if num_levels > MAX_LEVELS:
        sys.exit(
            f"error: computed {num_levels} levels exceeds maximum of "
            f"{MAX_LEVELS} (range {start_fan}%\u2192{end_fan}%, step {fan_step})"
        )
    return num_levels


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _resolve_common(args: argparse.Namespace) -> dict:
    """Resolve settings shared across the cooling pipeline."""
    num_levels = _validate_cooling_args(
        args.start_fan, args.end_fan,
        args.fan_step, args.level_height,
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
    brim_width = args.brim_width if args.brim_width is not _UNSET else None
    brim_sep = args.brim_separation if args.brim_separation is not _UNSET else None

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
        "brim_width": brim_width,
        "brim_sep": brim_sep,
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
        BASE_HEIGHT + args.level_height * _validate_cooling_args(
            args.start_fan, args.end_fan,
            args.fan_step, args.level_height,
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
    print(f"[DEBUG] Nozzle: {common['nozzle_size']} mm \u2192 "
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
    """Execute the cooling calibration pipeline."""
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
    brim_width = common["brim_width"]
    brim_sep = common["brim_sep"]

    if args.verbose:
        _debug_common(args, common, toml_config)

    config = CoolingTowerConfig(
        num_levels=num_levels,
        level_height=args.level_height,
        filament_type=args.filament_type,
    )
    out_dir = _resolve_output_dir(args.output_dir, prefix="cooling-")

    if args.verbose:
        print(
            f"[DEBUG] Cooling tower: {num_levels} levels, "
            f"{args.start_fan}\u2192{args.end_fan}%, "
            f"step={args.fan_step}"
        )
        print(f"[DEBUG] Output directory: {out_dir}")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"Fan: {args.start_fan}\u2192{args.end_fan}% "
        f"(step {args.fan_step})  "
        f"Temp: {nozzle_temp}\u00b0C  Bed: {bed_temp}\u00b0C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    suffix = gl.unique_suffix()
    safe_type = gl.safe_filename_part(config.filament_type)
    stl_name = (
        f"cooling_tower_{safe_type}"
        f"_{args.start_fan}_{args.fan_step}x{num_levels}"
        f"_{suffix}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model \u2192 {stl_path}")
    generate_cooling_tower_stl(config, stl_path)

    # --- Step 2: Slice ---
    gcode_ext = gl.gcode_ext(binary=not args.ascii_gcode)
    raw_gcode_path = str(
        out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}")
    )
    print(f"Slicing \u2192 {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    start_gcode, end_gcode = _render_gcode_templates(
        args, printer_name, nozzle_size, nozzle_temp, bed_temp,
    )
    if args.verbose and start_gcode is not None:
        print(f"[DEBUG] Rendered {printer_name} start/end G-code")

    result = slice_cooling_specimen(
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
        brim_width=brim_width,
        brim_separation=brim_sep,
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

    # --- Step 3: Insert cooling commands ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", gcode_ext))
    print(f"Inserting cooling commands \u2192 {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    gl.inject_thumbnails(
        gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose,
    )
    if printer_name is not None:
        gl.patch_slicer_metadata(
            gf, printer_name, nozzle_size, verbose=args.verbose,
        )
    levels = compute_cooling_levels(
        start_percent=args.start_fan,
        percent_step=args.fan_step,
        num_levels=num_levels,
        level_height=args.level_height,
        base_height=config.base_height,
    )
    if args.verbose:
        print("[DEBUG] Cooling levels:")
        for lv in levels:
            print(
                f"[DEBUG]   Z {lv.z_start:.1f}\u2013{lv.z_end:.1f} mm \u2192 "
                f"{lv.fan_percent}%"
            )

    gf.lines = insert_cooling_commands(gf.lines, levels)
    gf.lines = _patch_m862_nozzle_flags(
        gf.lines,
        nozzle_hardened=args.nozzle_hardened,
        nozzle_high_flow=args.nozzle_high_flow,
    )
    gl.save(gf, final_gcode_path)
    estimate = _print_estimate(gf, args.filament_type)

    # Print fan speed lookup table.
    print("\nFan speed by height:")
    for lv in levels:
        print(
            f"  Z {lv.z_start:5.1f} - {lv.z_end:5.1f} mm  "
            f"->  {lv.fan_percent}%"
        )
    print(
        "\nInspect print quality at each height "
        "to find your optimal fan speed.\n"
    )

    # --- Clean up intermediate files ---
    if not args.keep_files:
        Path(stl_path).unlink(missing_ok=True)
        Path(raw_gcode_path).unlink(missing_ok=True)

    # --- Step 4: Upload ---
    _upload(args, final_gcode_path)

    print("Done.")
    return estimate


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> Optional[Dict[str, str]]:
    """Execute the cooling calibration pipeline."""
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

    return _run_pipeline(args, toml_config)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point: parse arguments and run the pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args._explicit_keys = _explicit_keys(parser, argv)
    run(args)
