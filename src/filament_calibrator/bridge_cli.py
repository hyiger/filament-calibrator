"""Command-line interface for bridging calibration.

Orchestrates: model generation → standard slicing → thumbnail injection → upload.
No G-code parameter insertion is needed — the user prints the specimen,
inspects the underside of each bridge, and identifies the maximum span
length the printer can bridge cleanly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

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
from filament_calibrator.bridge_model import (
    BridgeTestConfig,
    generate_bridge_stl,
)
from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_THUMBNAILS,
    slice_bridge_specimen,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        prog="bridging-test",
        description=(
            "Generate, slice, and upload a bridging calibration specimen. "
            "The model consists of pillar pairs with bridges at different "
            "span lengths. Print the specimen, inspect the underside of "
            "each bridge, and identify the maximum span your printer can "
            "bridge cleanly."
        ),
    )

    # --- Model options ---
    type_names = ", ".join(_KNOWN_TYPES)
    model = p.add_argument_group("model options")
    model.add_argument(
        "--filament-type", type=str, default="PLA",
        help=(
            f"Filament type. Known presets ({type_names}) set defaults "
            "for --nozzle-temp, --bed-temp, and --fan-speed automatically. "
            "Custom names are accepted but require explicit temperatures. "
            "Default: PLA"
        ),
    )
    model.add_argument(
        "--spans", type=str, default="10,20,30,40,50,60",
        help=(
            "Comma-separated span distances between pillar pairs in mm. "
            "Default: 10,20,30,40,50,60"
        ),
    )
    model.add_argument(
        "--pillar-height", type=float, default=15.0,
        help="Height of bridge pillars in mm. Default: 15.0",
    )

    # --- Common options (nozzle, slicer, printer, output, verbosity) ---
    add_common_args(p)

    return p


def run(args: argparse.Namespace) -> Optional[Dict[str, str]]:
    """Execute the full bridging-test calibration pipeline.

    1. Generate a bridge test STL.
    2. Slice with standard settings.
    3. Inject thumbnails and metadata.
    4. Upload to the printer (unless ``--no-upload``).
    """
    # Load TOML config and apply defaults.
    toml_config = load_config(args.config)
    _apply_config(
        args, toml_config,
        explicit_keys=getattr(args, "_explicit_keys", None),
    )

    if args.verbose:
        cfg_path = _find_config_path(args.config)
        if cfg_path is not None:
            print(f"[DEBUG] Config file: {cfg_path}")
            print(f"[DEBUG] Config values: {_redact_config_for_debug(toml_config)}")
        else:
            print("[DEBUG] No config file loaded")

    # Fail fast: validate upload requirements.
    if not args.no_upload and (not args.printer_url or not args.api_key):
        print("Error: --printer-url and --api-key are required for upload.",
              file=sys.stderr)
        sys.exit(1)

    # Resolve filament preset for slicer settings.
    resolved = gl.resolve_filament_preset(
        args.filament_type,
        nozzle_temp=args.nozzle_temp if args.nozzle_temp is not _UNSET else None,
        bed_temp=args.bed_temp if args.bed_temp is not _UNSET else None,
        fan_speed=args.fan_speed if args.fan_speed is not _UNSET else None,
    )
    nozzle_temp: int = resolved["nozzle_temp"]
    bed_temp: int = resolved["bed_temp"]
    fan_speed: int = resolved["fan_speed"]

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

    _validate_printer_temps(printer_name, nozzle_temp, bed_temp)

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
    brim_width = args.brim_width if args.brim_width is not _UNSET else None
    brim_sep = args.brim_separation if args.brim_separation is not _UNSET else None

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

    try:
        spans = tuple(float(s.strip()) for s in args.spans.split(","))
    except ValueError:
        sys.exit(
            f"error: --spans requires comma-separated numbers, "
            f"got {args.spans!r}"
        )
    config = BridgeTestConfig(
        spans=spans,
        pillar_height=args.pillar_height,
        filament_type=args.filament_type,
    )
    out_dir = _resolve_output_dir(args.output_dir, prefix="bridging-test-")

    spans_str = ", ".join(f"{s:.0f}" for s in config.spans)

    if args.verbose:
        print(f"[DEBUG] Spans: {spans_str} mm")
        print(f"[DEBUG] Output directory: {out_dir}")

    print(
        f"Filament: {config.filament_type}  "
        f"Nozzle: {nozzle_size} mm  "
        f"Spans: {spans_str} mm  "
        f"Temp: {nozzle_temp}°C  Bed: {bed_temp}°C  Fan: {fan_speed}%"
    )

    # --- Step 1: Generate STL ---
    suffix = gl.unique_suffix()
    safe_type = gl.safe_filename_part(config.filament_type)
    stl_name = f"bridge_test_{safe_type}_{suffix}.stl"
    stl_path = str(out_dir / stl_name)
    print(f"Generating model → {stl_path}")
    generate_bridge_stl(config, stl_path)

    # --- Step 2: Slice with standard settings ---
    gcode_ext = gl.gcode_ext(binary=not args.ascii_gcode)
    raw_gcode_path = str(out_dir / stl_name.replace(".stl", f"_raw{gcode_ext}"))
    print(f"Slicing → {raw_gcode_path}")
    if args.verbose:
        effective_center = args.bed_center or f"{DEFAULT_BED_CENTER} (default)"
        print(f"[DEBUG] Bed center: {effective_center}")

    result = slice_bridge_specimen(
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
        brim_width=brim_width,
        brim_separation=brim_sep,
    )
    if args.verbose:
        print(f"[DEBUG] PrusaSlicer command: {' '.join(result.cmd)}")
        if result.stdout.strip():
            print(f"[DEBUG] PrusaSlicer stdout: {result.stdout.strip()}")

    if not result.ok:
        print(f"PrusaSlicer failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # --- Step 3: Inject thumbnails and metadata (no G-code insertion) ---
    final_gcode_path = str(out_dir / stl_name.replace(".stl", gcode_ext))
    print(f"Finalising → {final_gcode_path}")
    gf = gl.load(raw_gcode_path)
    gl.inject_thumbnails(gf, stl_path, DEFAULT_THUMBNAILS, verbose=args.verbose)
    if printer_name is not None:
        gl.patch_slicer_metadata(
            gf, printer_name, nozzle_size, verbose=args.verbose
        )
    gf.lines = _patch_m862_nozzle_flags(
        gf.lines,
        nozzle_hardened=args.nozzle_hardened,
        nozzle_high_flow=args.nozzle_high_flow,
    )
    gl.save(gf, final_gcode_path)
    estimate = _print_estimate(gf, args.filament_type)

    print("Bridge spans: " + ", ".join(f"{s:.0f}" for s in config.spans) + " mm")
    print(
        "Inspect the underside of each bridge to assess bridging "
        "quality at different span lengths."
    )

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
    return estimate


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point: parse arguments and run the pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args._explicit_keys = _explicit_keys(parser, argv)
    run(args)
