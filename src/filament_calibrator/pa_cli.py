"""Command-line interface for pressure advance calibration.

Supports two methods:

* **tower** — generates a hollow rectangular STL tower, slices with
  PrusaSlicer, and inserts PA commands at different Z levels.
* **pattern** — generates nested chevron (V-shape) STL patterns inside a
  frame, slices with PrusaSlicer, and inserts PA commands based on X position.
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
from filament_calibrator.pa_insert import (
    compute_pa_levels,
    compute_pa_pattern_regions,
    insert_pa_commands,
    insert_pa_pattern_commands,
)
from filament_calibrator.pa_model import (
    TOWER_DEPTH,
    TOWER_WIDTH,
    PATowerConfig,
    generate_pa_tower_stl,
)
from filament_calibrator.pa_pattern import (
    DEFAULT_ARM_LENGTH,
    DEFAULT_CORNER_ANGLE,
    DEFAULT_FRAME_NUM_LAYERS,
    DEFAULT_FRAME_OFFSET,
    DEFAULT_NUM_LAYERS,
    DEFAULT_PATTERN_SPACING,
    DEFAULT_WALL_COUNT,
    DEFAULT_WALL_THICKNESS,
    PAPatternConfig,
    generate_pa_pattern_stl,
    pattern_x_bounds,
    pattern_y_bounds,
    total_height as pattern_total_height,
)
from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_THUMBNAILS,
    slice_pa_pattern,
    slice_pa_specimen,
)


# Maximum number of PA levels to prevent excessively tall prints.
MAX_LEVELS = 50

# Valid calibration methods.
METHOD_CHOICES = ("tower", "pattern")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        prog="pressure-advance",
        description=(
            "Generate, slice, and upload a pressure advance calibration print. "
            "Tower method: hollow rectangular tower with PA by height. "
            "Pattern method: nested chevron shapes with PA by X position."
        ),
    )

    # --- PA options ---
    pa = p.add_argument_group("pressure advance options")
    pa.add_argument(
        "--start-pa", type=float, required=True,
        help="Starting PA value (bottom level / leftmost pattern).",
    )
    pa.add_argument(
        "--end-pa", type=float, required=True,
        help="Ending PA value (top level / rightmost pattern).",
    )
    pa.add_argument(
        "--pa-step", type=float, required=True,
        help="PA value increment per level / pattern.",
    )
    pa.add_argument(
        "--method", type=str, default="tower",
        choices=METHOD_CHOICES,
        help=(
            "Calibration method. 'tower' generates a hollow rectangular "
            "tower with PA increasing by height. 'pattern' generates "
            "nested chevron shapes, each with a different PA value. "
            "Default: tower"
        ),
    )

    # --- Model options ---
    type_names = ", ".join(_KNOWN_TYPES)
    model = p.add_argument_group("model options")
    model.add_argument(
        "--level-height", type=float, default=1.0,
        help="Height per PA level in mm (tower method). Default: 1.0",
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

    # --- Pattern method options ---
    pat = p.add_argument_group("pattern method options (--method pattern)")
    pat.add_argument(
        "--corner-angle", type=float, default=DEFAULT_CORNER_ANGLE,
        help=f"Chevron tip angle in degrees. Default: {DEFAULT_CORNER_ANGLE}",
    )
    pat.add_argument(
        "--arm-length", type=float, default=DEFAULT_ARM_LENGTH,
        help=f"Chevron arm length in mm. Default: {DEFAULT_ARM_LENGTH}",
    )
    pat.add_argument(
        "--wall-count", type=int, default=DEFAULT_WALL_COUNT,
        help=f"Number of concentric perimeters. Default: {DEFAULT_WALL_COUNT}",
    )
    pat.add_argument(
        "--num-layers", type=int, default=DEFAULT_NUM_LAYERS,
        help=f"Number of layers to print. Default: {DEFAULT_NUM_LAYERS}",
    )
    pat.add_argument(
        "--frame-layers", type=int, default=DEFAULT_FRAME_NUM_LAYERS,
        help=f"Number of layers for the frame/border. Default: {DEFAULT_FRAME_NUM_LAYERS}",
    )
    pat.add_argument(
        "--pattern-spacing", type=float, default=DEFAULT_PATTERN_SPACING,
        help=f"Perpendicular gap between chevron arms in mm. Default: {DEFAULT_PATTERN_SPACING}",
    )
    pat.add_argument(
        "--frame-offset", type=float, default=DEFAULT_FRAME_OFFSET,
        help=f"Frame margin around chevrons in mm. Default: {DEFAULT_FRAME_OFFSET}",
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
    nozzle.add_argument(
        "--nozzle-high-flow", action="store_true", default=False,
        help="Nozzle is a high-flow variant (sets F flag in M862.1).",
    )
    nozzle.add_argument(
        "--nozzle-hardened", action="store_true", default=False,
        help="Nozzle is hardened/abrasive-resistant (sets A flag in M862.1).",
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
    printer_names = ", ".join(sorted(gl.KNOWN_PRINTERS))
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
    level_height: float = 1.0,
) -> int:
    """Validate PA arguments and return the number of levels.

    Calls :func:`sys.exit` on invalid input.
    """
    if start_pa < 0:
        sys.exit(f"error: --start-pa must be non-negative (got {start_pa})")
    if pa_step <= 0:
        sys.exit(f"error: --pa-step must be positive (got {pa_step})")
    if level_height <= 0:
        sys.exit(
            f"error: --level-height must be positive (got {level_height})"
        )
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


# ---------------------------------------------------------------------------
# Shared pipeline helpers
# ---------------------------------------------------------------------------


def _resolve_common(args: argparse.Namespace) -> dict:
    """Resolve settings shared by both tower and pattern pipelines.

    Returns a dict with resolved values ready for use.
    """
    num_levels = _validate_pa_args(
        args.start_pa, args.end_pa, args.pa_step, args.level_height,
    )

    resolved = gl.resolve_filament_preset(
        args.filament_type,
        nozzle_temp=args.nozzle_temp if args.nozzle_temp is not _UNSET else None,
        bed_temp=args.bed_temp if args.bed_temp is not _UNSET else None,
        fan_speed=args.fan_speed if args.fan_speed is not _UNSET else None,
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
    model_width: float,
    model_depth: float,
    max_z: float,
) -> tuple[Optional[str], Optional[str]]:
    """Render printer-specific start/end G-code if applicable."""
    if printer_name is None or args.config_ini is not None:
        return None, None

    filament_preset = gl.FILAMENT_PRESETS.get(args.filament_type.upper())
    use_cool_fan = True
    if filament_preset is not None and filament_preset.get("enclosure"):
        use_cool_fan = False

    start_gcode = gl.render_start_gcode(
        printer_name,
        nozzle_dia=nozzle_size,
        bed_temp=bed_temp,
        hotend_temp=nozzle_temp,
        bed_center=args.bed_center or DEFAULT_BED_CENTER,
        model_width=model_width,
        model_depth=model_depth,
        cool_fan=use_cool_fan,
    )
    end_gcode = gl.render_end_gcode(
        printer_name,
        max_layer_z=max_z,
    )
    return start_gcode, end_gcode


# ---------------------------------------------------------------------------
# Tower pipeline
# ---------------------------------------------------------------------------


def _run_tower_pipeline(
    args: argparse.Namespace,
    toml_config: Dict[str, object],
) -> None:
    """Execute the tower-method PA calibration pipeline."""
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

    config = PATowerConfig(
        num_levels=num_levels,
        level_height=args.level_height,
        filament_type=args.filament_type,
    )
    out_dir = _resolve_output_dir(args.output_dir, prefix="pressure-advance-")

    if args.verbose:
        print(f"[DEBUG] PA tower: {num_levels} levels, "
              f"{args.start_pa}→{args.end_pa}, step={args.pa_step}")
        print(f"[DEBUG] Output directory: {out_dir}")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"PA: {args.start_pa}→{args.end_pa} (step {args.pa_step})  "
        f"Temp: {nozzle_temp}°C  Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    suffix = gl.unique_suffix()
    safe_type = gl.safe_filename_part(config.filament_type)
    stl_name = (
        f"pa_tower_{safe_type}"
        f"_{args.start_pa}_{args.pa_step}x{num_levels}"
        f"_{suffix}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    generate_pa_tower_stl(config, stl_path)

    # --- Step 2: Slice ---
    gcode_ext = gl.gcode_ext(binary=not args.ascii_gcode)
    raw_gcode_path = str(out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}"))
    print(f"Slicing → {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    total_z = num_levels * args.level_height
    start_gcode, end_gcode = _render_gcode_templates(
        args, printer_name, nozzle_size, nozzle_temp, bed_temp,
        TOWER_WIDTH, TOWER_DEPTH, total_z,
    )
    if args.verbose and start_gcode is not None:
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
    gl.inject_thumbnails(gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose)
    if printer_name is not None:
        gl.patch_slicer_metadata(
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

    gf.lines = insert_pa_commands(
        gf.lines, levels,
        printer=printer_name or "COREONE",
    )
    gf.lines = _patch_m862_nozzle_flags(
        gf.lines,
        nozzle_hardened=args.nozzle_hardened,
        nozzle_high_flow=args.nozzle_high_flow,
    )
    gl.save(gf, final_gcode_path)

    # Print PA level lookup table for the user.
    print("\nPA value by height:")
    for lv in levels:
        print(f"  Z {lv.z_start:5.1f} - {lv.z_end:5.1f} mm  ->  PA {lv.pa_value:.4f}")
    print("\nMeasure the height with the sharpest corners to find your optimal PA value.\n")

    # --- Clean up intermediate files ---
    if not args.keep_files:
        Path(stl_path).unlink(missing_ok=True)
        Path(raw_gcode_path).unlink(missing_ok=True)

    # --- Step 4: Upload ---
    _upload(args, final_gcode_path)

    print("Done.")


# ---------------------------------------------------------------------------
# Pattern pipeline
# ---------------------------------------------------------------------------


def _parse_bed_center_x(bed_center: str) -> float:
    """Extract and validate the X coordinate from a ``--bed-center`` string.

    Expected format is ``"X,Y"`` where both parts are numeric.
    Calls :func:`sys.exit` with a clear message on malformed input.
    """
    parts = bed_center.split(",")
    if len(parts) != 2:
        sys.exit(
            f"error: --bed-center must be in X,Y format (got {bed_center!r})"
        )
    try:
        return float(parts[0])
    except ValueError:
        sys.exit(
            f"error: --bed-center X value is not a number "
            f"(got {parts[0]!r} from {bed_center!r})"
        )


def _run_pattern_pipeline(
    args: argparse.Namespace,
    toml_config: Dict[str, object],
) -> None:
    """Execute the pattern-method PA calibration pipeline."""
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

    config = PAPatternConfig(
        num_patterns=num_levels,
        corner_angle=args.corner_angle,
        arm_length=args.arm_length,
        wall_count=args.wall_count,
        num_layers=args.num_layers,
        pattern_spacing=args.pattern_spacing,
        wall_thickness=DEFAULT_WALL_THICKNESS,
        frame_offset=args.frame_offset,
        frame_num_layers=args.frame_layers,
        layer_height=layer_height,
        filament_type=args.filament_type,
    )
    out_dir = _resolve_output_dir(args.output_dir, prefix="pressure-advance-")

    if args.verbose:
        print(f"[DEBUG] PA pattern: {num_levels} chevrons, "
              f"{args.start_pa}→{args.end_pa}, step={args.pa_step}")
        print(f"[DEBUG] Chevron: angle={config.corner_angle}° "
              f"arm={config.arm_length}mm "
              f"walls={config.wall_count}")
        print(f"[DEBUG] Output directory: {out_dir}")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"PA: {args.start_pa}→{args.end_pa} (step {args.pa_step})  "
        f"Temp: {nozzle_temp}°C  Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    suffix = gl.unique_suffix()
    safe_type = gl.safe_filename_part(config.filament_type)
    stl_name = (
        f"pa_pattern_{safe_type}"
        f"_{args.start_pa}_{args.pa_step}x{num_levels}"
        f"_{suffix}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    pa_values = [
        round(args.start_pa + i * args.pa_step, 4)
        for i in range(num_levels)
    ]
    _, x_tips = generate_pa_pattern_stl(config, stl_path, pa_values=pa_values)

    # --- Step 2: Slice ---
    gcode_ext = gl.gcode_ext(binary=not args.ascii_gcode)
    raw_gcode_path = str(out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}"))
    print(f"Slicing → {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    model_height = pattern_total_height(config)
    x_min, x_max = pattern_x_bounds(config, x_tips)
    model_width = x_max - x_min
    y_min, y_max = pattern_y_bounds(config, include_labels=True)
    model_depth = y_max - y_min

    start_gcode, end_gcode = _render_gcode_templates(
        args, printer_name, nozzle_size, nozzle_temp, bed_temp,
        model_width, model_depth, model_height,
    )
    if args.verbose and start_gcode is not None:
        print(f"[DEBUG] Rendered {printer_name} start/end G-code")

    result = slice_pa_pattern(
        stl_path=stl_path,
        output_gcode_path=raw_gcode_path,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        perimeters=config.wall_count,
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

    # --- Step 3: Insert PA commands by X position ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", gcode_ext))
    print(f"Inserting PA commands → {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    gl.inject_thumbnails(gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose)
    if printer_name is not None:
        gl.patch_slicer_metadata(
            gf, printer_name, nozzle_size, verbose=args.verbose
        )

    # x_tips are model-space coordinates.  PrusaSlicer's --center uses the
    # model bounding-box center, so we shift tips by the same translation.
    bed_cx = float(DEFAULT_BED_CENTER.split(",")[0])
    if args.bed_center is not None:
        bed_cx = _parse_bed_center_x(args.bed_center)
    model_cx = (x_min + x_max) / 2.0
    x_shift = bed_cx - model_cx
    shifted_tips = [tx + x_shift for tx in x_tips]

    regions = compute_pa_pattern_regions(pa_values, shifted_tips)
    if args.verbose:
        print("[DEBUG] PA regions:")
        for r in regions:
            xs = f"{r.x_start:.1f}" if r.x_start != float("-inf") else "-inf"
            xe = f"{r.x_end:.1f}" if r.x_end != float("inf") else "+inf"
            print(f"[DEBUG]   X {xs} – {xe} → PA {r.pa_value:.4f}")

    gf.lines = insert_pa_pattern_commands(
        gf.lines, regions,
        printer=printer_name or "COREONE",
    )
    gf.lines = _patch_m862_nozzle_flags(
        gf.lines,
        nozzle_hardened=args.nozzle_hardened,
        nozzle_high_flow=args.nozzle_high_flow,
    )
    gl.save(gf, final_gcode_path)

    # Print PA pattern reference table for the user.
    print("\nPA value by pattern position:")
    for i, (pa, cx) in enumerate(zip(pa_values, shifted_tips)):
        print(f"  Pattern {i + 1:2d} (X ≈ {cx:6.1f} mm)  ->  PA {pa:.4f}")
    print("\nInspect which chevron has the sharpest corners to find your optimal PA value.\n")

    # --- Clean up intermediate files ---
    if not args.keep_files:
        Path(stl_path).unlink(missing_ok=True)
        Path(raw_gcode_path).unlink(missing_ok=True)

    # --- Step 4: Upload ---
    _upload(args, final_gcode_path)

    print("Done.")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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
# Entry points
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> None:
    """Execute the pressure advance calibration pipeline.

    Dispatches to the tower or pattern method based on ``--method``.
    """
    # Load TOML config and apply defaults.
    toml_config = load_config(args.config)
    _apply_config(
        args, toml_config,
        explicit_keys=getattr(args, "_explicit_keys", None),
    )

    # Fail fast: validate upload requirements.
    if not args.no_upload and (not args.printer_url or not args.api_key):
        print("Error: --printer-url and --api-key are required for upload.",
              file=sys.stderr)
        sys.exit(1)

    method = getattr(args, "method", "tower")
    if method == "pattern":
        _run_pattern_pipeline(args, toml_config)
    else:
        _run_tower_pipeline(args, toml_config)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point: parse arguments and run the pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args._explicit_keys = _explicit_keys(parser, argv)
    run(args)
