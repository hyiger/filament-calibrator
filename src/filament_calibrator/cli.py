"""Command-line interface for filament temperature tower calibration.

Orchestrates: model generation → slicing → temp insertion → upload.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import gcode_lib as gl

from filament_calibrator.config import _find_config_path, load_config
from filament_calibrator.model import TowerConfig, generate_tower_stl
from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_THUMBNAILS,
    slice_tower,
)
from filament_calibrator.tempinsert import compute_temp_tiers, insert_temperatures

# Sentinel used to detect whether the user explicitly supplied a value.
_UNSET = object()

# Known filament type names from gcode-lib presets.
_KNOWN_TYPES = sorted(gl.FILAMENT_PRESETS.keys())

# Reasonable hotend temperature bounds for validation.
MIN_PRINT_TEMP = 150   # °C — below this no common filament prints
MAX_PRINT_TEMP = 350   # °C — above this is outside consumer hotend range


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
            "for --start-temp, --bed-temp, and --fan-speed automatically. "
            "Custom names are accepted but require explicit temperatures. "
            "Default: PLA"
        ),
    )
    model.add_argument(
        "--start-temp", type=int, default=_UNSET,
        help=(
            "Highest temperature in °C (bottom tier). "
            "Default: from filament preset temp_max."
        ),
    )
    model.add_argument(
        "--end-temp", type=int, default=_UNSET,
        help=(
            "Lowest temperature in °C (top tier). "
            "Default: from filament preset temp_min."
        ),
    )
    model.add_argument(
        "--temp-step", type=int, default=5,
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

    # --- Nozzle options ---
    nozzle = p.add_argument_group("nozzle options")
    nozzle.add_argument(
        "--nozzle-size", type=float, default=0.4,
        help=(
            "Nozzle diameter in mm. Sets appropriate defaults for "
            "layer height (nozzle × 0.5) and extrusion width "
            "(nozzle × 1.125). Default: 0.4"
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
        "--bed-center", type=str, default=None,
        help=(
            "Bed centre as X,Y in mm (e.g. 125,110). Used to position the "
            "model on the print bed. Default: 125,110 (Prusa 250×220 bed)."
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


# Argparse defaults for config-eligible string/flag fields.
_ARGPARSE_DEFAULTS: Dict[str, object] = {
    "printer_url": None,
    "api_key": None,
    "prusaslicer_path": None,
    "config_ini": None,
    "filament_type": "PLA",
    "output_dir": None,
    "bed_center": None,
    "nozzle_size": 0.4,
    "nozzle_high_flow": False,
    "nozzle_hardened": False,
    "printer": "COREONE",
}


def _apply_config(
    args: argparse.Namespace,
    config: Dict[str, object],
    *,
    explicit_keys: Optional[frozenset[str]] = None,
) -> None:
    """Apply TOML config values to *args* where the user didn't supply a CLI value.

    When *explicit_keys* is provided (a frozenset of attribute names that
    the user explicitly passed on the command line), those attributes are
    never overwritten — even if the CLI value happens to match the
    argparse default.

    When *explicit_keys* is ``None`` (legacy callers), the function falls
    back to the previous heuristic: an attribute is overwritten only when
    its current value equals the built-in default in ``_ARGPARSE_DEFAULTS``.

    Mutates *args* in place.
    """
    for attr, value in config.items():
        if attr not in _ARGPARSE_DEFAULTS:
            continue
        # If the caller told us exactly which keys the user supplied, use
        # that set as the ground truth.
        if explicit_keys is not None:
            if attr in explicit_keys:
                continue
        else:
            current = getattr(args, attr, _ARGPARSE_DEFAULTS[attr])
            if current != _ARGPARSE_DEFAULTS[attr]:
                continue
        setattr(args, attr, value)


def _explicit_keys(
    parser: argparse.ArgumentParser,
    argv: Optional[List[str]],
) -> frozenset[str]:
    """Return the set of argparse dest names explicitly supplied on the CLI.

    Re-parses *argv* (or ``sys.argv[1:]`` when *argv* is ``None``) against
    *parser* to discover which options the user actually typed.  The
    returned frozenset contains attribute (dest) names only for those
    options.
    """
    # Snapshot the parser's default values, then set every optional to
    # a private sentinel so we can detect which ones the user supplied.
    sentinel = object()
    saved: Dict[str, object] = {}
    for action in parser._actions:
        if action.option_strings:  # skip positional args
            saved[action.dest] = action.default
            action.default = sentinel

    try:
        ns = parser.parse_args(argv)
    finally:
        for action in parser._actions:
            if action.dest in saved:
                action.default = saved[action.dest]

    return frozenset(
        dest for dest, val in vars(ns).items() if val is not sentinel
    )


_M862_PATTERN = re.compile(r"(M862\.1\s+P[\d.]+)(?:\s+A\d)?(?:\s+F\d)?(.*)")


def _patch_m862_nozzle_flags(
    lines: List[gl.GCodeLine],
    *,
    nozzle_hardened: bool = False,
    nozzle_high_flow: bool = False,
) -> List[gl.GCodeLine]:
    """Append ``A`` and ``F`` flags to ``M862.1`` nozzle-check commands.

    ``A1`` = hardened/abrasive-resistant nozzle, ``F1`` = high-flow nozzle.
    Existing ``A``/``F`` flags are stripped before re-inserting so the
    transform is idempotent.
    """
    a_flag = 1 if nozzle_hardened else 0
    f_flag = 1 if nozzle_high_flow else 0
    result: List[gl.GCodeLine] = []
    for line in lines:
        raw = line.raw if isinstance(line, gl.GCodeLine) else line
        m = _M862_PATTERN.match(raw)
        if m:
            patched = f"{m.group(1)} A{a_flag} F{f_flag}{m.group(2)}"
            result.append(gl.parse_line(patched))
        else:
            result.append(line)
    return result


def _resolve_output_dir(
    output_dir: Optional[str],
    prefix: str = "filament-calibrator-",
) -> Path:
    """Resolve the output directory, creating it if needed."""
    if output_dir:
        p = Path(output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return Path(tempfile.mkdtemp(prefix=prefix))


def _validate_printer_temps(
    printer_name: Optional[str],
    nozzle_temp: int,
    bed_temp: int,
) -> None:
    """Exit if temps exceed the selected printer's hardware limits."""
    if printer_name is None:
        return
    specs = gl.PRINTER_PRESETS.get(printer_name)
    if specs is None:
        return
    max_nozzle = specs.get("max_nozzle_temp")
    max_bed = specs.get("max_bed_temp")
    if max_nozzle is not None and nozzle_temp > max_nozzle:
        sys.exit(
            f"error: nozzle temp {nozzle_temp}°C exceeds {printer_name} "
            f"max of {int(max_nozzle)}°C"
        )
    if max_bed is not None and bed_temp > max_bed:
        sys.exit(
            f"error: bed temp {bed_temp}°C exceeds {printer_name} "
            f"max of {int(max_bed)}°C"
        )


def _resolve_preset(args: argparse.Namespace) -> Dict[str, object]:
    """Look up the filament preset and return resolved settings.

    Returns a dict with keys ``start_temp``, ``end_temp``, ``bed_temp``,
    ``fan_speed``.  Values come from the preset when the user did not
    supply explicit CLI overrides.

    Preset ``temp_max`` / ``temp_min`` are used directly as the default
    start and end temperatures.  This function is specific to the
    temperature-tower CLI.
    """
    filament_key = args.filament_type.upper()
    preset = gl.FILAMENT_PRESETS.get(filament_key)

    if preset is not None:
        default_start = int(preset["temp_max"])
        default_end = int(preset["temp_min"])
        default_bed = int(preset["bed"])
        default_fan = int(preset["fan"])
    else:
        default_start = 230
        default_end = 190
        default_bed = 60
        default_fan = 100

    return {
        "start_temp": args.start_temp if args.start_temp is not _UNSET else default_start,
        "end_temp": args.end_temp if args.end_temp is not _UNSET else default_end,
        "bed_temp": args.bed_temp if args.bed_temp is not _UNSET else default_bed,
        "fan_speed": args.fan_speed if args.fan_speed is not _UNSET else default_fan,
    }


def _compute_num_tiers(start_temp: int, end_temp: int, temp_step: int) -> int:
    """Compute the number of tiers from a temperature range.

    Validates inputs and calls :func:`sys.exit` on failure:

    * *temp_step* must be positive.
    * Both temperatures must be within ``MIN_PRINT_TEMP``–``MAX_PRINT_TEMP``.
    * *start_temp* must be ≥ *end_temp* + *temp_step* (at least 2 tiers).
    * The range must be evenly divisible by *temp_step*.
    * The result must be at most 10 tiers.
    """
    if temp_step <= 0:
        sys.exit(
            f"error: --temp-step must be positive (got {temp_step})"
        )
    for label, temp in [("--start-temp", start_temp), ("--end-temp", end_temp)]:
        if temp < MIN_PRINT_TEMP or temp > MAX_PRINT_TEMP:
            sys.exit(
                f"error: {label} {temp}°C is outside the normal printing "
                f"range ({MIN_PRINT_TEMP}–{MAX_PRINT_TEMP}°C)"
            )
    if start_temp < end_temp + temp_step:
        sys.exit(
            "error: --start-temp must be at least --end-temp + --temp-step "
            f"(got {start_temp} < {end_temp} + {temp_step})"
        )
    spread = start_temp - end_temp
    if spread % temp_step != 0:
        sys.exit(
            f"error: temperature range {spread}°C "
            f"is not evenly divisible by --temp-step {temp_step}"
        )
    num_tiers = spread // temp_step + 1
    if num_tiers > 10:
        sys.exit(
            f"error: computed {num_tiers} tiers exceeds maximum of 10 "
            f"(range {start_temp}→{end_temp}°C, step {temp_step})"
        )
    return num_tiers


def _build_tower_config(
    args: argparse.Namespace,
    start_temp: int,
    end_temp: int,
) -> TowerConfig:
    """Build a TowerConfig from parsed CLI arguments."""
    num_tiers = _compute_num_tiers(start_temp, end_temp, args.temp_step)
    return TowerConfig(
        start_temp=start_temp,
        temp_step=args.temp_step,
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
    # Load TOML config and apply defaults before anything else.
    toml_config = load_config(args.config)
    _apply_config(
        args, toml_config,
        explicit_keys=getattr(args, "_explicit_keys", None),
    )

    if args.verbose:
        cfg_path = _find_config_path(args.config)
        if cfg_path is not None:
            print(f"[DEBUG] Config file: {cfg_path}")
            print(f"[DEBUG] Config values: {toml_config}")
        else:
            print("[DEBUG] No config file loaded")

    # Fail fast: validate upload requirements before expensive pipeline steps.
    if not args.no_upload and (not args.printer_url or not args.api_key):
        print("Error: --printer-url and --api-key are required for upload.",
              file=sys.stderr)
        sys.exit(1)

    resolved = _resolve_preset(args)
    start_temp: int = resolved["start_temp"]
    end_temp: int = resolved["end_temp"]
    bed_temp: int = resolved["bed_temp"]
    fan_speed: int = resolved["fan_speed"]

    if args.verbose:
        filament_key = args.filament_type.upper()
        preset = gl.FILAMENT_PRESETS.get(filament_key)
        if preset is not None:
            print(f"[DEBUG] Filament preset '{filament_key}' found")
        else:
            print(f"[DEBUG] Filament type '{filament_key}' not in presets, "
                  "using fallback defaults")
        print(f"[DEBUG] Resolved: start_temp={start_temp} end_temp={end_temp} "
              f"bed_temp={bed_temp} fan_speed={fan_speed}")

    config = _build_tower_config(args, start_temp, end_temp)
    out_dir = _resolve_output_dir(args.output_dir, prefix="temperature-tower-")

    if args.verbose:
        print(f"[DEBUG] Tower: {config.num_tiers} tiers, "
              f"{start_temp}→{end_temp}°C, step={config.temp_step}°C")
        print(f"[DEBUG] Output directory: {out_dir}")

    # Resolve printer model for bed dimensions and metadata.
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

    _validate_printer_temps(printer_name, start_temp, bed_temp)

    # Derive layer height and extrusion width from nozzle size.
    nozzle_size: float = args.nozzle_size
    layer_height = round(nozzle_size * 0.5, 2)
    extrusion_width = round(nozzle_size * 1.125, 2)

    if args.verbose:
        print(f"[DEBUG] Nozzle: {nozzle_size} mm → "
              f"layer_height={layer_height} extrusion_width={extrusion_width}")
        if printer_name is not None:
            print(f"[DEBUG] Printer: {printer_name} "
                  f"(bed center: {args.bed_center})")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"Range: {start_temp}→{end_temp}°C  "
        f"Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    suffix = gl.unique_suffix()
    safe_type = gl.safe_filename_part(config.filament_type)
    stl_name = (
        f"temp_tower_{safe_type}"
        f"_{config.start_temp}_{config.temp_step}x{config.num_tiers}"
        f"_{suffix}.stl"
    )
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    generate_tower_stl(config, stl_path)

    # --- Step 2: Slice ---
    gcode_ext = gl.gcode_ext(binary=not args.ascii_gcode)
    raw_gcode_path = str(out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}"))
    print(f"Slicing → {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    result = slice_tower(
        stl_path=stl_path,
        output_gcode_path=raw_gcode_path,
        config_ini=args.config_ini,
        prusaslicer_path=args.prusaslicer_path,
        extra_args=args.extra_slicer_args,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_temp=start_temp,
        bed_center=args.bed_center,
        bed_shape=bed_shape,
        nozzle_diameter=nozzle_size,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
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

    # --- Step 3: Insert temperatures ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", gcode_ext))
    print(f"Inserting temperatures → {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    gl.inject_thumbnails(gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose)
    if printer_name is not None:
        gl.patch_slicer_metadata(
            gf, printer_name, nozzle_size, verbose=args.verbose
        )
    tiers = compute_temp_tiers(
        start_temp=config.start_temp,
        temp_step=config.temp_step,
        num_tiers=config.num_tiers,
    )
    if args.verbose:
        print("[DEBUG] Temperature tiers:")
        for t in tiers:
            print(f"[DEBUG]   Z {t.z_start:.1f}–{t.z_end:.1f} mm → {t.temp}°C")

    gf.lines = insert_temperatures(gf.lines, tiers)
    gf.lines = _patch_m862_nozzle_flags(
        gf.lines,
        nozzle_hardened=args.nozzle_hardened,
        nozzle_high_flow=args.nozzle_high_flow,
    )
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
    args._explicit_keys = _explicit_keys(parser, argv)
    run(args)
