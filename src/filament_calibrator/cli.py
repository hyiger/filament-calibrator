"""Command-line interface for filament temperature tower calibration.

Orchestrates: model generation → slicing → temp insertion → upload.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import gcode_lib as gl

from filament_calibrator.model import TowerConfig, generate_tower_stl
from filament_calibrator.slicer import slice_tower
from filament_calibrator.tempinsert import compute_temp_tiers, insert_temperatures

# Sentinel used to detect whether the user explicitly supplied a value.
_UNSET = object()

# Known filament type names from gcode-lib presets.
_KNOWN_TYPES = sorted(gl.FILAMENT_PRESETS.keys())


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        prog="temperature-tower",
        description="Generate, slice, and upload a filament temperature tower.",
    )

    type_names = ", ".join(_KNOWN_TYPES)

    # --- Model options ---
    model = p.add_argument_group("model options")
    model.add_argument(
        "--filament-type", type=str, default="PLA",
        help=(
            f"Filament type. Known presets ({type_names}) set defaults "
            "for --high-temp, --bed-temp, and --fan-speed automatically. "
            "Custom names are accepted but require explicit temperatures. "
            "Default: PLA"
        ),
    )
    model.add_argument(
        "--high-temp", type=int, default=_UNSET,
        help=(
            "Highest temperature in °C (bottom tier). "
            "Default: from filament preset temp_max."
        ),
    )
    model.add_argument(
        "--low-temp", type=int, default=_UNSET,
        help=(
            "Lowest temperature in °C (top tier). "
            "Default: from filament preset temp_min."
        ),
    )
    model.add_argument(
        "--temp-jump", type=int, default=5,
        help="Temperature decrease per tier in °C. Default: 5",
    )
    model.add_argument(
        "--brand-top", type=str, default="",
        help="Optional brand label on top of the tower.",
    )
    model.add_argument(
        "--brand-bottom", type=str, default="",
        help="Optional brand label on the bottom of the base.",
    )

    # --- Slicer options ---
    slicer = p.add_argument_group("slicer options")
    slicer.add_argument(
        "--bed-temp", type=int, default=_UNSET,
        help="Bed temperature in °C. Default: from filament preset.",
    )
    slicer.add_argument(
        "--fan-speed", type=int, default=_UNSET,
        help="Fan speed 0–100%%. Default: from filament preset.",
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
        "--extra-slicer-args", type=str, nargs=argparse.REMAINDER, default=None,
        help="Additional raw CLI arguments for PrusaSlicer (must be last).",
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

    return p


def _resolve_output_dir(output_dir: Optional[str]) -> Path:
    """Resolve the output directory, creating it if needed."""
    if output_dir:
        p = Path(output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return Path(tempfile.mkdtemp(prefix="temperature-tower-"))


def resolve_preset(args: argparse.Namespace) -> Dict[str, object]:
    """Look up the filament preset and return resolved settings.

    Returns a dict with keys ``high_temp``, ``low_temp``, ``bed_temp``,
    ``fan_speed``.  Values come from the preset when the user did not
    supply explicit CLI overrides.

    Preset ``temp_max`` / ``temp_min`` are used directly as the default
    high and low temperatures.
    """
    filament_key = args.filament_type.upper()
    preset = gl.FILAMENT_PRESETS.get(filament_key)

    if preset is not None:
        default_high = int(preset["temp_max"])
        default_low = int(preset["temp_min"])
        default_bed = int(preset["bed"])
        default_fan = int(preset["fan"])
    else:
        default_high = 230
        default_low = 190
        default_bed = 60
        default_fan = 100

    return {
        "high_temp": args.high_temp if args.high_temp is not _UNSET else default_high,
        "low_temp": args.low_temp if args.low_temp is not _UNSET else default_low,
        "bed_temp": args.bed_temp if args.bed_temp is not _UNSET else default_bed,
        "fan_speed": args.fan_speed if args.fan_speed is not _UNSET else default_fan,
    }


def _compute_num_tiers(high_temp: int, low_temp: int, temp_jump: int) -> int:
    """Compute the number of tiers from a temperature range.

    Validates that *high_temp* > *low_temp*, that the range is evenly
    divisible by *temp_jump*, and that the result is at most 10 tiers.
    Calls :func:`sys.exit` with a clear message on validation failure.
    """
    if high_temp <= low_temp:
        sys.exit(
            "error: --high-temp must be greater than --low-temp "
            f"(got {high_temp} and {low_temp})"
        )
    spread = high_temp - low_temp
    if spread % temp_jump != 0:
        sys.exit(
            f"error: temperature range {spread}°C "
            f"is not evenly divisible by --temp-jump {temp_jump}"
        )
    num_tiers = spread // temp_jump + 1
    if num_tiers > 10:
        sys.exit(
            f"error: computed {num_tiers} tiers exceeds maximum of 10 "
            f"(range {high_temp}→{low_temp}°C, step {temp_jump})"
        )
    return num_tiers


def _build_tower_config(
    args: argparse.Namespace,
    high_temp: int,
    low_temp: int,
) -> TowerConfig:
    """Build a TowerConfig from parsed CLI arguments."""
    num_tiers = _compute_num_tiers(high_temp, low_temp, args.temp_jump)
    return TowerConfig(
        high_temp=high_temp,
        temp_jump=args.temp_jump,
        num_tiers=num_tiers,
        filament_type=args.filament_type,
        brand_top=args.brand_top,
        brand_bottom=args.brand_bottom,
    )


def run(args: argparse.Namespace) -> None:
    """Execute the full calibration pipeline.

    1. Resolve filament preset defaults.
    2. Generate the temp tower STL model.
    3. Slice the STL with PrusaSlicer.
    4. Insert temperature changes into the G-code.
    5. Upload to the printer (unless ``--no-upload``).
    """
    # Fail fast: validate upload requirements before expensive pipeline steps.
    if not args.no_upload and (not args.printer_url or not args.api_key):
        print("Error: --printer-url and --api-key are required for upload.",
              file=sys.stderr)
        sys.exit(1)

    resolved = resolve_preset(args)
    high_temp: int = resolved["high_temp"]
    low_temp: int = resolved["low_temp"]
    bed_temp: int = resolved["bed_temp"]
    fan_speed: int = resolved["fan_speed"]

    config = _build_tower_config(args, high_temp, low_temp)
    out_dir = _resolve_output_dir(args.output_dir)
    print(
        f"Filament: {config.filament_type}  "
        f"Range: {high_temp}→{low_temp}°C  "
        f"Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    stl_name = (
        f"temp_tower_{config.filament_type}"
        f"_{config.high_temp}_{config.temp_jump}x{config.num_tiers}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    generate_tower_stl(config, stl_path)

    # --- Step 2: Slice ---
    raw_gcode_path = str(out_dir / stl_name.replace(".stl", "_raw.gcode"))
    print(f"Slicing → {raw_gcode_path}")
    result = slice_tower(
        stl_path=stl_path,
        output_gcode_path=raw_gcode_path,
        config_ini=args.config_ini,
        prusaslicer_path=args.prusaslicer_path,
        extra_args=args.extra_slicer_args,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_temp=high_temp,
    )
    if not result.ok:
        print(f"PrusaSlicer failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # --- Step 3: Insert temperatures ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", ".gcode"))
    print(f"Inserting temperatures → {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    tiers = compute_temp_tiers(
        high_temp=config.high_temp,
        temp_jump=config.temp_jump,
        num_tiers=config.num_tiers,
    )
    gf.lines = insert_temperatures(gf.lines, tiers)
    gl.save(gf, final_gcode_path)

    # --- Clean up intermediate files ---
    if not args.keep_files:
        Path(stl_path).unlink(missing_ok=True)
        Path(raw_gcode_path).unlink(missing_ok=True)

    # --- Step 4: Upload ---
    if not args.no_upload:
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
