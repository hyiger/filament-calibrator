"""Streamlit GUI for filament calibration tools.

Provides a browser-based interface to the temperature-tower,
extrusion-multiplier, volumetric-flow, and pressure-advance CLI
pipelines.  All heavy lifting (CAD, slicing, G-code processing)
runs server-side.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import gcode_lib as gl

from filament_calibrator.cli import _KNOWN_TYPES
from filament_calibrator.config import load_config
from filament_calibrator.ini_writer import (
    CalibrationResults,
    build_change_summary,
    merge_results_into_ini,
)


# ---------------------------------------------------------------------------
# Helpers (importable without Streamlit for testing)
# ---------------------------------------------------------------------------

_FALLBACK_PRESET: Dict[str, Any] = {
    "hotend": 210,
    "bed": 60,
    "fan": 100,
    "temp_min": 190,
    "temp_max": 230,
    "enclosure": False,
}

_NOZZLE_SIZES: List[float] = [0.25, 0.3, 0.4, 0.5, 0.6, 0.8]

_PRINTER_LIST: List[str] = sorted(gl.KNOWN_PRINTERS)


def get_preset(filament_type: str) -> Dict[str, Any]:
    """Return filament preset defaults for *filament_type*.

    Falls back to safe defaults for unknown types.
    """
    preset = gl.FILAMENT_PRESETS.get(filament_type.upper())
    if preset is not None:
        return {
            "hotend": int(preset["hotend"]),
            "bed": int(preset["bed"]),
            "fan": int(preset["fan"]),
            "temp_min": int(preset["temp_min"]),
            "temp_max": int(preset["temp_max"]),
            "enclosure": bool(preset.get("enclosure", False)),
        }
    return dict(_FALLBACK_PRESET)


def run_pipeline(
    run_fn: Callable[[argparse.Namespace], None],
    args: argparse.Namespace,
) -> Tuple[bool, str]:
    """Execute a CLI ``run()`` function, capturing stdout/stderr.

    Returns ``(success, captured_output)``.
    """
    buf = io.StringIO()
    success = True
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            run_fn(args)
    except SystemExit as exc:
        success = exc.code in (0, None)
    except Exception as exc:
        buf.write(f"\nUnexpected error: {exc}\n")
        success = False
    return success, buf.getvalue()


def _check_printer_temps(
    printer: str,
    nozzle_temp: int,
    bed_temp: int,
) -> Optional[str]:
    """Return an error message if temps exceed the printer's limits, else None."""
    printer_name: Optional[str]
    try:
        printer_name = gl.resolve_printer(printer)
    except ValueError:
        return None
    specs = gl.PRINTER_PRESETS.get(printer_name)
    if specs is None:
        return None
    max_nozzle = specs.get("max_nozzle_temp")
    max_bed = specs.get("max_bed_temp")
    if max_nozzle is not None and nozzle_temp > max_nozzle:
        return (
            f"Nozzle temp {nozzle_temp}°C exceeds {printer_name} "
            f"max of {int(max_nozzle)}°C"
        )
    if max_bed is not None and bed_temp > max_bed:
        return (
            f"Bed temp {bed_temp}°C exceeds {printer_name} "
            f"max of {int(max_bed)}°C"
        )
    return None


def build_temp_tower_namespace(
    *,
    filament_type: str,
    start_temp: int,
    end_temp: int,
    temp_step: int,
    bed_temp: int,
    fan_speed: int,
    brand_top: str,
    brand_bottom: str,
    nozzle_size: float,
    nozzle_high_flow: bool = False,
    nozzle_hardened: bool = False,
    printer: str,
    ascii_gcode: bool,
    output_dir: str,
    config_ini: Optional[str],
    prusaslicer_path: Optional[str],
    printer_url: Optional[str],
    api_key: Optional[str],
    no_upload: bool,
    print_after_upload: bool,
) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` for the temperature-tower pipeline."""
    return argparse.Namespace(
        filament_type=filament_type,
        start_temp=start_temp,
        end_temp=end_temp,
        temp_step=temp_step,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        brand_top=brand_top,
        brand_bottom=brand_bottom,
        nozzle_size=nozzle_size,
        nozzle_high_flow=nozzle_high_flow,
        nozzle_hardened=nozzle_hardened,
        printer=printer,
        ascii_gcode=ascii_gcode,
        output_dir=output_dir,
        config_ini=config_ini or None,
        prusaslicer_path=prusaslicer_path or None,
        bed_center=None,
        extra_slicer_args=None,
        printer_url=printer_url or None,
        api_key=api_key or None,
        no_upload=no_upload,
        print_after_upload=print_after_upload,
        config=None,
        keep_files=True,
        verbose=True,
    )


def build_flow_namespace(
    *,
    filament_type: str,
    start_speed: float,
    end_speed: float,
    step: float,
    level_height: float,
    nozzle_temp: int,
    bed_temp: int,
    fan_speed: int,
    nozzle_size: float,
    nozzle_high_flow: bool = False,
    nozzle_hardened: bool = False,
    layer_height: float,
    extrusion_width: float,
    printer: str,
    ascii_gcode: bool,
    output_dir: str,
    config_ini: Optional[str],
    prusaslicer_path: Optional[str],
    printer_url: Optional[str],
    api_key: Optional[str],
    no_upload: bool,
    print_after_upload: bool,
) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` for the volumetric-flow pipeline."""
    return argparse.Namespace(
        filament_type=filament_type,
        start_speed=start_speed,
        end_speed=end_speed,
        step=step,
        level_height=level_height,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_size=nozzle_size,
        nozzle_high_flow=nozzle_high_flow,
        nozzle_hardened=nozzle_hardened,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        printer=printer,
        ascii_gcode=ascii_gcode,
        output_dir=output_dir,
        config_ini=config_ini or None,
        prusaslicer_path=prusaslicer_path or None,
        bed_center=None,
        extra_slicer_args=None,
        printer_url=printer_url or None,
        api_key=api_key or None,
        no_upload=no_upload,
        print_after_upload=print_after_upload,
        config=None,
        keep_files=True,
        verbose=True,
    )


def build_pa_namespace(
    *,
    filament_type: str,
    start_pa: float,
    end_pa: float,
    pa_step: float,
    method: str = "tower",
    level_height: float = 1.0,
    nozzle_temp: int,
    bed_temp: int,
    fan_speed: int,
    nozzle_size: float,
    nozzle_high_flow: bool = False,
    nozzle_hardened: bool = False,
    layer_height: float,
    extrusion_width: float,
    corner_angle: float = 90.0,
    arm_length: float = 40.0,
    wall_count: int = 3,
    num_layers: int = 4,
    frame_layers: int = 1,
    pattern_spacing: float = 1.6,
    frame_offset: float = 0.0,
    printer: str,
    ascii_gcode: bool,
    output_dir: str,
    config_ini: Optional[str],
    prusaslicer_path: Optional[str],
    printer_url: Optional[str],
    api_key: Optional[str],
    no_upload: bool,
    print_after_upload: bool,
) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` for the pressure-advance pipeline."""
    return argparse.Namespace(
        filament_type=filament_type,
        start_pa=start_pa,
        end_pa=end_pa,
        pa_step=pa_step,
        method=method,
        level_height=level_height,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_size=nozzle_size,
        nozzle_high_flow=nozzle_high_flow,
        nozzle_hardened=nozzle_hardened,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        corner_angle=corner_angle,
        arm_length=arm_length,
        wall_count=wall_count,
        num_layers=num_layers,
        frame_layers=frame_layers,
        pattern_spacing=pattern_spacing,
        frame_offset=frame_offset,
        printer=printer,
        ascii_gcode=ascii_gcode,
        output_dir=output_dir,
        config_ini=config_ini or None,
        prusaslicer_path=prusaslicer_path or None,
        bed_center=None,
        extra_slicer_args=None,
        printer_url=printer_url or None,
        api_key=api_key or None,
        no_upload=no_upload,
        print_after_upload=print_after_upload,
        config=None,
        keep_files=True,
        verbose=True,
    )


def build_em_namespace(
    *,
    filament_type: str,
    cube_size: float,
    nozzle_temp: int,
    bed_temp: int,
    fan_speed: int,
    nozzle_size: float,
    nozzle_high_flow: bool = False,
    nozzle_hardened: bool = False,
    layer_height: float,
    extrusion_width: float,
    printer: str,
    ascii_gcode: bool,
    output_dir: str,
    config_ini: Optional[str],
    prusaslicer_path: Optional[str],
    printer_url: Optional[str],
    api_key: Optional[str],
    no_upload: bool,
    print_after_upload: bool,
) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` for the extrusion-multiplier pipeline."""
    return argparse.Namespace(
        filament_type=filament_type,
        cube_size=cube_size,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_size=nozzle_size,
        nozzle_high_flow=nozzle_high_flow,
        nozzle_hardened=nozzle_hardened,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        printer=printer,
        ascii_gcode=ascii_gcode,
        output_dir=output_dir,
        config_ini=config_ini or None,
        prusaslicer_path=prusaslicer_path or None,
        bed_center=None,
        extra_slicer_args=None,
        printer_url=printer_url or None,
        api_key=api_key or None,
        no_upload=no_upload,
        print_after_upload=print_after_upload,
        config=None,
        keep_files=True,
        verbose=True,
    )


def build_retraction_namespace(
    *,
    filament_type: str,
    start_retraction: float,
    end_retraction: float,
    retraction_step: float,
    level_height: float = 1.0,
    nozzle_temp: int,
    bed_temp: int,
    fan_speed: int,
    nozzle_size: float,
    nozzle_high_flow: bool = False,
    nozzle_hardened: bool = False,
    layer_height: float,
    extrusion_width: float,
    printer: str,
    ascii_gcode: bool,
    output_dir: str,
    config_ini: Optional[str],
    prusaslicer_path: Optional[str],
    printer_url: Optional[str],
    api_key: Optional[str],
    no_upload: bool,
    print_after_upload: bool,
) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` for the retraction-test pipeline."""
    return argparse.Namespace(
        filament_type=filament_type,
        start_retraction=start_retraction,
        end_retraction=end_retraction,
        retraction_step=retraction_step,
        level_height=level_height,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_size=nozzle_size,
        nozzle_high_flow=nozzle_high_flow,
        nozzle_hardened=nozzle_hardened,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        printer=printer,
        ascii_gcode=ascii_gcode,
        output_dir=output_dir,
        config_ini=config_ini or None,
        prusaslicer_path=prusaslicer_path or None,
        bed_center=None,
        extra_slicer_args=None,
        printer_url=printer_url or None,
        api_key=api_key or None,
        no_upload=no_upload,
        print_after_upload=print_after_upload,
        config=None,
        keep_files=True,
        verbose=True,
    )


def build_shrinkage_namespace(
    *,
    filament_type: str,
    arm_length: float,
    nozzle_temp: int,
    bed_temp: int,
    fan_speed: int,
    nozzle_size: float,
    nozzle_high_flow: bool = False,
    nozzle_hardened: bool = False,
    layer_height: float,
    extrusion_width: float,
    printer: str,
    ascii_gcode: bool,
    output_dir: str,
    config_ini: Optional[str],
    prusaslicer_path: Optional[str],
    printer_url: Optional[str],
    api_key: Optional[str],
    no_upload: bool,
    print_after_upload: bool,
) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` for the shrinkage-test pipeline."""
    return argparse.Namespace(
        filament_type=filament_type,
        arm_length=arm_length,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_size=nozzle_size,
        nozzle_high_flow=nozzle_high_flow,
        nozzle_hardened=nozzle_hardened,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        printer=printer,
        ascii_gcode=ascii_gcode,
        output_dir=output_dir,
        config_ini=config_ini or None,
        prusaslicer_path=prusaslicer_path or None,
        bed_center=None,
        extra_slicer_args=None,
        printer_url=printer_url or None,
        api_key=api_key or None,
        no_upload=no_upload,
        print_after_upload=print_after_upload,
        config=None,
        keep_files=True,
        verbose=True,
    )


def _fresh_output_dir(custom_output_dir: str) -> str:
    """Return *custom_output_dir* if set, otherwise a fresh temp directory.

    Each pipeline run gets its own directory so that output files from
    a previous run (e.g. a temperature tower) are never confused with
    the current run (e.g. a flow specimen).
    """
    if custom_output_dir:
        return custom_output_dir
    return tempfile.mkdtemp(prefix="fc-gui-")


def find_output_file(output_dir: str, ascii_gcode: bool) -> Optional[Path]:
    """Find the most recent final G-code file in *output_dir*.

    Selects the newest file by modification time so that a shared output
    directory with files from previous runs returns the correct result.
    """
    ext = ".gcode" if ascii_gcode else ".bgcode"
    candidates = [
        f for f in Path(output_dir).glob(f"*{ext}")
        if "_raw" not in f.name
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


# ---------------------------------------------------------------------------
# Native file/directory dialogs (subprocess-based for macOS safety)
# ---------------------------------------------------------------------------


def _open_file_dialog(
    title: str = "Select File",
    filetypes: Optional[List[Tuple[str, str]]] = None,
) -> Optional[str]:
    """Open a native file chooser and return the selected path.

    On macOS uses ``osascript`` (AppleScript) for a reliable native
    dialog.  On other platforms falls back to ``tkinter.filedialog``
    in a subprocess.

    Returns ``None`` if the user cancels or an error occurs.
    """
    if platform.system() == "Darwin":
        return _osascript_file_dialog(title, filetypes)
    return _tkinter_file_dialog(title, filetypes)


def _open_directory_dialog(
    title: str = "Select Directory",
) -> Optional[str]:
    """Open a native directory chooser and return the selected path.

    On macOS uses ``osascript`` (AppleScript).  On other platforms
    falls back to ``tkinter.filedialog`` in a subprocess.

    Returns ``None`` if the user cancels or an error occurs.
    """
    if platform.system() == "Darwin":
        return _osascript_directory_dialog(title)
    return _tkinter_directory_dialog(title)


# --- macOS osascript dialogs ---


def _osascript_file_dialog(
    title: str,
    filetypes: Optional[List[Tuple[str, str]]] = None,
) -> Optional[str]:
    """Open a macOS-native file chooser via ``osascript``."""
    # Build "of type" clause from filetypes, e.g. *.ini → "ini"
    type_clause = ""
    if filetypes:
        exts = []
        for _label, pattern in filetypes:
            ext = pattern.lstrip("*.")
            if ext and ext != "*":
                exts.append(f'"{ext}"')
        if exts:
            type_clause = f" of type {{{', '.join(exts)}}}"

    applescript = (
        f'POSIX path of (choose file with prompt "{title}"{type_clause})'
    )
    return _run_osascript(applescript)


def _osascript_directory_dialog(title: str) -> Optional[str]:
    """Open a macOS-native directory chooser via ``osascript``."""
    applescript = f'POSIX path of (choose folder with prompt "{title}")'
    return _run_osascript(applescript)


def _run_osascript(script: str) -> Optional[str]:
    """Run an AppleScript via ``osascript`` and return stdout or None."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path if path else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# --- tkinter fallback (non-macOS) ---


def _tkinter_file_dialog(
    title: str,
    filetypes: Optional[List[Tuple[str, str]]] = None,
) -> Optional[str]:
    """Open a tkinter file chooser in a subprocess."""
    ft_json = json.dumps(filetypes or [])
    script = (
        "import json, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk(); root.withdraw()\n"
        "root.attributes('-topmost', True)\n"
        f"ft = [tuple(x) for x in json.loads({ft_json!r})]\n"
        "if ft:\n"
        "    ft.append(('All files', '*'))\n"
        f"path = filedialog.askopenfilename(title={title!r}, filetypes=ft or ())\n"
        "print(path or '')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path if path else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _tkinter_directory_dialog(title: str) -> Optional[str]:
    """Open a tkinter directory chooser in a subprocess."""
    script = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk(); root.withdraw()\n"
        "root.attributes('-topmost', True)\n"
        f"path = filedialog.askdirectory(title={title!r})\n"
        "print(path or '')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path if path else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# ---------------------------------------------------------------------------
# TOML config auto-populate
# ---------------------------------------------------------------------------


def apply_toml_to_session(
    state: Dict[str, Any],
    toml_cfg: Dict[str, Any],
) -> None:
    """Apply TOML config values to Streamlit session state on first load.

    Only writes keys that are **not yet present** in *state*, so user
    edits and browse-dialog results are never overwritten.
    """
    _mapping: Dict[str, str] = {
        "printer_url": "printer_url",
        "api_key": "api_key",
        "config_ini": "config_ini",
        "prusaslicer_path": "prusaslicer_path",
        "output_dir": "output_dir",
    }
    for toml_key, state_key in _mapping.items():
        if toml_key in toml_cfg and state_key not in state:
            state[state_key] = str(toml_cfg[toml_key])

    if "filament_type" in toml_cfg:
        ft = toml_cfg["filament_type"].upper()
        if ft in _KNOWN_TYPES and "_toml_filament_type" not in state:
            state["_toml_filament_type"] = ft

    if "nozzle_size" in toml_cfg:
        ns = toml_cfg["nozzle_size"]
        if isinstance(ns, (int, float)):
            snapped = snap_nozzle_size(float(ns))
            if snapped in _NOZZLE_SIZES and "_toml_nozzle_size" not in state:
                state["_toml_nozzle_size"] = snapped

    if "printer" in toml_cfg:
        pr = toml_cfg["printer"].upper()
        if pr in _PRINTER_LIST and "_toml_printer" not in state:
            state["_toml_printer"] = pr

    if "nozzle_high_flow" in toml_cfg and "_toml_nozzle_high_flow" not in state:
        state["_toml_nozzle_high_flow"] = bool(toml_cfg["nozzle_high_flow"])

    if "nozzle_hardened" in toml_cfg and "_toml_nozzle_hardened" not in state:
        state["_toml_nozzle_hardened"] = bool(toml_cfg["nozzle_hardened"])


# ---------------------------------------------------------------------------
# INI auto-populate helpers
# ---------------------------------------------------------------------------


def snap_nozzle_size(diameter: float) -> float:
    """Snap *diameter* to the nearest value in :data:`_NOZZLE_SIZES`."""
    return min(_NOZZLE_SIZES, key=lambda s: abs(s - diameter))


def apply_ini_to_session(
    state: Dict[str, Any],
    ini_vals: Dict[str, Any],
    *,
    sidebar: bool = True,
) -> None:
    """Write parsed ``.ini`` values into Streamlit session-state widget keys.

    Must be called **before** widgets render so that Streamlit picks up
    the updated values.  Only keys present in *ini_vals* are written.

    Parameters
    ----------
    sidebar:
        When *False*, skip sidebar widget keys (``sidebar_nozzle_size``,
        ``sidebar_printer``, ``sidebar_filament_type``).  Use this for
        the post-widget-defaults re-apply where sidebar widgets have
        already been instantiated.
    """
    if "nozzle_temp" in ini_vals:
        nt = ini_vals["nozzle_temp"]
        state["em_nozzle_temp"] = nt
        state["flow_nozzle_temp"] = nt
        state["pa_nozzle_temp"] = nt
        state["retraction_nozzle_temp"] = nt
        # Derive a temp tower range centred on the INI temperature.
        state["tt_start_temp"] = nt + 15
        state["tt_end_temp"] = nt - 15

    if "bed_temp" in ini_vals:
        bt = ini_vals["bed_temp"]
        state["tt_bed_temp"] = bt
        state["em_bed_temp"] = bt
        state["flow_bed_temp"] = bt
        state["pa_bed_temp"] = bt
        state["retraction_bed_temp"] = bt

    if "fan_speed" in ini_vals:
        fs = ini_vals["fan_speed"]
        state["tt_fan"] = fs
        state["em_fan"] = fs
        state["flow_fan"] = fs
        state["pa_fan"] = fs
        state["retraction_fan"] = fs

    if "layer_height" in ini_vals:
        lh = ini_vals["layer_height"]
        state["em_lh"] = lh
        state["flow_lh"] = lh
        state["pa_lh"] = lh
        state["retraction_lh"] = lh

    if "extrusion_width" in ini_vals:
        ew = ini_vals["extrusion_width"]
        state["em_ew"] = ew
        state["flow_ew"] = ew
        state["pa_ew"] = ew
        state["retraction_ew"] = ew

    if sidebar and "nozzle_diameter" in ini_vals:
        snapped = snap_nozzle_size(ini_vals["nozzle_diameter"])
        if snapped in _NOZZLE_SIZES:
            state["sidebar_nozzle_size"] = snapped

    if sidebar and "printer_model" in ini_vals:
        pm = ini_vals["printer_model"].upper()
        if pm in _PRINTER_LIST:
            state["sidebar_printer"] = pm

    if sidebar and "filament_type" in ini_vals:
        ft = ini_vals["filament_type"].upper()
        state["sidebar_filament_type"] = ft

    if sidebar and "nozzle_high_flow" in ini_vals:
        state["sidebar_nozzle_high_flow"] = ini_vals["nozzle_high_flow"]

    if sidebar and "nozzle_hardened" in ini_vals:
        state["sidebar_nozzle_hardened"] = ini_vals["nozzle_hardened"]


# ---------------------------------------------------------------------------
# PrusaLink upload helper
# ---------------------------------------------------------------------------


def upload_to_printer(
    printer_url: str,
    api_key: str,
    gcode_path: str,
    print_after_upload: bool = False,
) -> Tuple[bool, str]:
    """Upload G-code to a PrusaLink printer.

    Calls :func:`gcode_lib.prusalink_upload` and returns a
    ``(success, message)`` tuple.  Any exception from the upload is
    caught and reported as a failure message.
    """
    try:
        filename = gl.prusalink_upload(
            base_url=printer_url,
            api_key=api_key,
            gcode_path=gcode_path,
            print_after_upload=print_after_upload,
        )
        msg = f"Uploaded as: {filename}"
        if print_after_upload:
            msg += "\nPrint started."
        return True, msg
    except Exception as exc:
        return False, f"Upload failed: {exc}"


def build_calibration_results(
    *,
    set_temp: bool,
    temperature: int,
    set_flow: bool,
    max_volumetric_speed: float,
    set_pa: bool,
    pa_value: float,
    set_em: bool,
    extrusion_multiplier: float,
    set_retraction: bool,
    retraction_length: float,
    printer: str,
) -> CalibrationResults:
    """Build a :class:`CalibrationResults` from GUI widget values.

    Checkbox flags (``set_*``) gate which values are included;
    unchecked values are stored as ``None``.  The *printer* name
    determines the PA G-code command (M572 for most Prusa printers,
    M900 for the Mini).
    """
    return CalibrationResults(
        temperature=temperature if set_temp else None,
        max_volumetric_speed=max_volumetric_speed if set_flow else None,
        pa_value=pa_value if set_pa else None,
        extrusion_multiplier=extrusion_multiplier if set_em else None,
        retraction_length=retraction_length if set_retraction else None,
        printer=printer,
    )


# ---------------------------------------------------------------------------
# Streamlit app (only imported when actually running the GUI)
# ---------------------------------------------------------------------------

def _app() -> None:  # pragma: no cover
    """Main Streamlit application."""
    import streamlit as st

    from filament_calibrator.cli import run as temp_run
    from filament_calibrator.em_cli import run as em_run
    from filament_calibrator.flow_cli import run as flow_run
    from filament_calibrator.pa_cli import run as pa_run
    from filament_calibrator.retraction_cli import run as retraction_run
    from filament_calibrator.shrinkage_cli import run as shrinkage_run

    st.set_page_config(
        page_title="Filament Calibrator",
        layout="wide",
    )
    st.title("Filament Calibrator")

    # Load TOML config defaults on first render only.
    if "_toml_loaded" not in st.session_state:
        st.session_state["_toml_loaded"] = True
        try:
            _toml = load_config()
        except SystemExit:
            _toml = {}
        if _toml:
            apply_toml_to_session(st.session_state, _toml)

    # Apply pending browse-dialog results before widgets render.
    for _key in ("config_ini", "prusaslicer_path", "output_dir"):
        _pending = f"_pending_{_key}"
        if _pending in st.session_state:
            st.session_state[_key] = st.session_state.pop(_pending)

    # Parse .ini and auto-populate fields when the path changes.
    # _ini_vals is kept alive so that, after _widget_defaults overwrites
    # tab keys with preset defaults, we can re-apply INI overrides.
    _ini_vals: Dict[str, Any] = {}
    _cur_ini = st.session_state.get("config_ini", "")
    _prev_ini = st.session_state.get("_prev_config_ini", "")
    _ini_cleared = bool(_prev_ini and not _cur_ini)
    if _cur_ini != _prev_ini:
        st.session_state["_prev_config_ini"] = _cur_ini
        if _cur_ini and Path(_cur_ini).is_file():
            try:
                _ini_vals = gl.parse_prusaslicer_ini(_cur_ini)
            except Exception:
                _ini_vals = {}
            if _ini_vals:
                apply_ini_to_session(st.session_state, _ini_vals)

    # Selectbox defaults (must be set before widgets render).
    # Uses TOML values as defaults on first load; .ini values are written
    # directly to these keys by apply_ini_to_session() and take priority.
    if "sidebar_filament_type" not in st.session_state:
        st.session_state["sidebar_filament_type"] = (
            st.session_state.get("_toml_filament_type", "PLA")
        )
    if "sidebar_printer" not in st.session_state:
        st.session_state["sidebar_printer"] = (
            st.session_state.get("_toml_printer", "COREONE")
        )
    if "sidebar_nozzle_size" not in st.session_state:
        st.session_state["sidebar_nozzle_size"] = (
            st.session_state.get("_toml_nozzle_size", 0.4)
        )
    if "sidebar_nozzle_high_flow" not in st.session_state:
        st.session_state["sidebar_nozzle_high_flow"] = (
            st.session_state.get("_toml_nozzle_high_flow", False)
        )
    if "sidebar_nozzle_hardened" not in st.session_state:
        st.session_state["sidebar_nozzle_hardened"] = (
            st.session_state.get("_toml_nozzle_hardened", False)
        )

    # --- Sidebar: shared settings ---
    with st.sidebar:
        st.header("Common Settings")

        # Build options list; include any custom type from .ini that isn't
        # in the preset list so the dropdown reflects the config exactly.
        _ft_options = list(_KNOWN_TYPES)
        _cur_ft = st.session_state.get("sidebar_filament_type", "PLA")
        if _cur_ft not in _ft_options:
            _ft_options.insert(0, _cur_ft)

        filament_type = st.selectbox(
            "Filament Type",
            options=_ft_options,
            key="sidebar_filament_type",
        )
        preset = get_preset(filament_type)

        printer = st.selectbox(
            "Printer",
            options=_PRINTER_LIST,
            key="sidebar_printer",
        )

        nozzle_size = st.selectbox(
            "Nozzle Size (mm)",
            options=_NOZZLE_SIZES,
            key="sidebar_nozzle_size",
        )
        _nozzle_indent, _nozzle_col = st.columns([0.12, 0.88])
        with _nozzle_col:
            nozzle_high_flow = st.checkbox(
                "High Flow",
                key="sidebar_nozzle_high_flow",
                help="Nozzle is a high-flow variant (sets F flag in M862.1)",
            )
            nozzle_hardened = st.checkbox(
                "Hardened",
                key="sidebar_nozzle_hardened",
                help="Nozzle is hardened/abrasive-resistant (sets A flag in M862.1)",
            )

        ascii_gcode = st.checkbox(
            "ASCII G-code (.gcode)",
            value=False,
            help="Default is binary (.bgcode) with thumbnail previews",
        )

        st.divider()
        st.subheader("PrusaLink Upload")
        _has_upload_cfg = bool(
            st.session_state.get("printer_url")
            and st.session_state.get("api_key")
        )
        enable_upload = st.checkbox(
            "Upload to printer", value=_has_upload_cfg,
        )
        printer_url = ""
        api_key = ""
        if enable_upload:
            printer_url = st.text_input(
                "Printer URL",
                placeholder="http://192.168.1.100",
                key="printer_url",
            )
            api_key = st.text_input(
                "API Key", type="password", key="api_key",
            )

        st.divider()
        st.subheader("Advanced")

        col_ini, col_ini_btn = st.columns([5, 1])
        with col_ini:
            config_ini = st.text_input(
                "PrusaSlicer config (.ini)",
                placeholder="Leave empty for built-in defaults",
                key="config_ini",
            )
        with col_ini_btn:
            st.markdown("<div style='padding-top:28px'></div>",
                        unsafe_allow_html=True)
            if st.button("📂", key="browse_ini",
                         help="Browse for .ini config"):
                path = _open_file_dialog(
                    title="Select PrusaSlicer config",
                    filetypes=[("INI files", "*.ini")],
                )
                if path:
                    st.session_state["_pending_config_ini"] = path
                    st.rerun()

        col_ps, col_ps_btn = st.columns([5, 1])
        with col_ps:
            prusaslicer_path = st.text_input(
                "PrusaSlicer path",
                placeholder="Auto-detect",
                key="prusaslicer_path",
            )
        with col_ps_btn:
            st.markdown("<div style='padding-top:28px'></div>",
                        unsafe_allow_html=True)
            if st.button("📂", key="browse_ps",
                         help="Browse for PrusaSlicer"):
                path = _open_file_dialog(
                    title="Select PrusaSlicer executable",
                )
                if path:
                    st.session_state["_pending_prusaslicer_path"] = path
                    st.rerun()

        col_od, col_od_btn = st.columns([5, 1])
        with col_od:
            custom_output_dir = st.text_input(
                "Output directory",
                placeholder="Auto (temp directory)",
                key="output_dir",
            )
        with col_od_btn:
            st.markdown("<div style='padding-top:28px'></div>",
                        unsafe_allow_html=True)
            if st.button("📂", key="browse_dir",
                         help="Browse for directory"):
                path = _open_directory_dialog(
                    title="Select output directory",
                )
                if path:
                    st.session_state["_pending_output_dir"] = path
                    st.rerun()

    # --- Derived values ---
    derived_lh = round(nozzle_size * 0.5, 2)
    derived_ew = round(nozzle_size * 1.125, 2)

    # Set default session-state values for keyed widgets.
    #
    # On first render *or* when the filament preset / nozzle size changes,
    # force-write new preset defaults so every tab reflects the updated
    # values.  If an .ini was loaded in this same render cycle, its
    # explicit values are re-applied afterwards so they always win.
    _prev_ft = st.session_state.get("_preset_filament_type")
    _prev_ns = st.session_state.get("_preset_nozzle_size")
    _defaults_changed = (
        _prev_ft != filament_type or _prev_ns != nozzle_size or _ini_cleared
    )
    if _defaults_changed:
        st.session_state["_preset_filament_type"] = filament_type
        st.session_state["_preset_nozzle_size"] = nozzle_size

    _widget_defaults = {
        "tt_start_temp": preset["temp_max"],
        "tt_end_temp": preset["temp_min"],
        "tt_bed_temp": preset["bed"],
        "tt_fan": preset["fan"],
        "em_nozzle_temp": preset["hotend"],
        "em_bed_temp": preset["bed"],
        "em_fan": preset["fan"],
        "em_lh": derived_lh,
        "em_ew": derived_ew,
        "flow_nozzle_temp": preset["hotend"],
        "flow_bed_temp": preset["bed"],
        "flow_fan": preset["fan"],
        "flow_lh": derived_lh,
        "flow_ew": derived_ew,
        "pa_nozzle_temp": preset["hotend"],
        "pa_bed_temp": preset["bed"],
        "pa_fan": preset["fan"],
        "pa_lh": derived_lh,
        "pa_ew": derived_ew,
        "retraction_nozzle_temp": preset["hotend"],
        "retraction_bed_temp": preset["bed"],
        "retraction_fan": preset["fan"],
        "retraction_lh": derived_lh,
        "retraction_ew": derived_ew,
        "shrinkage_nozzle_temp": preset["hotend"],
        "shrinkage_bed_temp": preset["bed"],
        "shrinkage_fan": preset["fan"],
        "shrinkage_lh": derived_lh,
        "shrinkage_ew": derived_ew,
    }
    for _wk, _wv in _widget_defaults.items():
        if _wk not in st.session_state or _defaults_changed:
            st.session_state[_wk] = _wv

    # Re-apply INI overrides — explicit config values take priority
    # over preset defaults.  sidebar=False because sidebar widgets have
    # already been instantiated and Streamlit forbids setting their keys.
    if _ini_vals:
        apply_ini_to_session(st.session_state, _ini_vals, sidebar=False)

    # --- Tabs ---
    (tab_temp, tab_em, tab_flow, tab_pa, tab_retraction,
     tab_shrinkage, tab_results) = st.tabs([
        "Temperature Tower", "Extrusion Multiplier", "Volumetric Flow",
        "Pressure Advance", "Retraction Test", "Shrinkage", "Results",
    ])

    # === Tab 1: Temperature Tower ===
    with tab_temp:
        st.subheader("Temperature Tower")
        st.caption(
            "Generate a tower that prints at decreasing temperatures "
            "from bottom to top to find optimal print temperature."
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            start_temp = st.number_input(
                "Start Temp (\u00b0C) \u2014 bottom",
                min_value=150,
                max_value=350,
                step=5,
                key="tt_start_temp",
            )
        with col2:
            end_temp = st.number_input(
                "End Temp (\u00b0C) \u2014 top",
                min_value=150,
                max_value=350,
                step=5,
                key="tt_end_temp",
            )
        with col3:
            temp_step = st.number_input(
                "Temp Step (\u00b0C)",
                value=5,
                min_value=1,
                max_value=50,
                step=1,
            )

        col4, col5 = st.columns(2)
        with col4:
            tt_bed_temp = st.number_input(
                "Bed Temp (\u00b0C)",
                min_value=0,
                max_value=150,
                key="tt_bed_temp",
            )
        with col5:
            tt_fan_speed = st.number_input(
                "Fan Speed (%)",
                min_value=0,
                max_value=100,
                key="tt_fan",
            )

        col6, col7 = st.columns(2)
        with col6:
            brand_top = st.text_input("Brand Label (top)", value="")
        with col7:
            brand_bottom = st.text_input("Brand Label (bottom)", value="")

        # Tier count preview
        spread = start_temp - end_temp
        if spread > 0 and temp_step > 0 and spread % temp_step == 0:
            num_tiers = spread // temp_step + 1
            st.info(f"{num_tiers} tiers: {start_temp}\u00b0C \u2192 {end_temp}\u00b0C")
        elif spread <= 0:
            st.warning("Start temp must be higher than end temp.")

        if st.button("Generate Temperature Tower", type="primary",
                      key="run_temp"):
            _temp_err = _check_printer_temps(printer, start_temp, tt_bed_temp)
            if _temp_err:
                st.error(_temp_err)
                st.stop()
            run_dir = _fresh_output_dir(custom_output_dir)
            args = build_temp_tower_namespace(
                filament_type=filament_type,
                start_temp=start_temp,
                end_temp=end_temp,
                temp_step=temp_step,
                bed_temp=tt_bed_temp,
                fan_speed=tt_fan_speed,
                brand_top=brand_top,
                brand_bottom=brand_bottom,
                nozzle_size=nozzle_size,
                nozzle_high_flow=nozzle_high_flow,
                nozzle_hardened=nozzle_hardened,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=None,
                api_key=None,
                no_upload=True,
                print_after_upload=False,
            )
            with st.spinner("Running temperature tower pipeline..."):
                success, log = run_pipeline(temp_run, args)
            st.session_state["_last_run"] = {
                "output_dir": run_dir,
                "ascii_gcode": ascii_gcode,
                "success": success,
                "log": log,
                "tab": "temp",
                "upload_enabled": enable_upload,
                "printer_url": printer_url,
                "api_key": api_key,
            }
            st.session_state.pop("_upload_status", None)
            st.session_state.pop("_upload_message", None)
            st.session_state.pop("_print_after", None)
            st.session_state.pop("upload_print_after", None)

        _run = st.session_state.get("_last_run")
        if _run and _run["tab"] == "temp":
            _show_results(st, _run)

    # === Tab 2: Extrusion Multiplier ===
    with tab_em:
        st.subheader("Extrusion Multiplier")
        st.caption(
            "Generate a 40mm cube sliced in vase mode with classic walls. "
            "Print it, measure the wall thickness with calipers, and "
            "calculate: EM = expected_width / measured_width."
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            em_nozzle_temp = st.number_input(
                "Nozzle Temp (\u00b0C)",
                min_value=150,
                max_value=350,
                key="em_nozzle_temp",
            )
        with col2:
            em_bed_temp = st.number_input(
                "Bed Temp (\u00b0C)",
                min_value=0,
                max_value=150,
                key="em_bed_temp",
            )
        with col3:
            em_fan = st.number_input(
                "Fan Speed (%)",
                min_value=0,
                max_value=100,
                key="em_fan",
            )

        with st.expander("Advanced Slicer Settings"):
            em_cube_size = st.number_input(
                "Cube Size (mm)",
                value=40.0,
                min_value=5.0,
                max_value=200.0,
                step=5.0,
                key="em_cube_size",
            )
            em_layer_height = st.number_input(
                "Layer Height (mm)",
                min_value=0.05,
                max_value=1.0,
                format="%.2f",
                key="em_lh",
            )
            em_extrusion_width = st.number_input(
                "Extrusion Width (mm)",
                min_value=0.1,
                max_value=2.0,
                format="%.2f",
                key="em_ew",
            )

        st.info(f"Expected wall thickness: {em_extrusion_width:.2f} mm")

        if st.button("Generate EM Cube", type="primary",
                      key="run_em"):
            _temp_err = _check_printer_temps(
                printer, em_nozzle_temp, em_bed_temp,
            )
            if _temp_err:
                st.error(_temp_err)
                st.stop()
            run_dir = _fresh_output_dir(custom_output_dir)
            args = build_em_namespace(
                filament_type=filament_type,
                cube_size=em_cube_size,
                nozzle_temp=em_nozzle_temp,
                bed_temp=em_bed_temp,
                fan_speed=em_fan,
                nozzle_size=nozzle_size,
                nozzle_high_flow=nozzle_high_flow,
                nozzle_hardened=nozzle_hardened,
                layer_height=em_layer_height,
                extrusion_width=em_extrusion_width,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=None,
                api_key=None,
                no_upload=True,
                print_after_upload=False,
            )
            with st.spinner("Running extrusion multiplier pipeline..."):
                success, log = run_pipeline(em_run, args)
            st.session_state["_last_run"] = {
                "output_dir": run_dir,
                "ascii_gcode": ascii_gcode,
                "success": success,
                "log": log,
                "tab": "em",
                "upload_enabled": enable_upload,
                "printer_url": printer_url,
                "api_key": api_key,
            }
            st.session_state.pop("_upload_status", None)
            st.session_state.pop("_upload_message", None)
            st.session_state.pop("_print_after", None)
            st.session_state.pop("upload_print_after", None)

        _run = st.session_state.get("_last_run")
        if _run and _run["tab"] == "em":
            _show_results(st, _run)

    # === Tab 3: Volumetric Flow ===
    with tab_flow:
        st.subheader("Volumetric Flow")
        st.caption(
            "Generate a serpentine vase-mode specimen with increasing "
            "print speeds to find maximum volumetric flow rate."
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            start_speed = st.number_input(
                "Start Speed (mm\u00b3/s)",
                value=5.0,
                min_value=0.1,
                step=0.5,
                format="%.1f",
            )
        with col2:
            end_speed = st.number_input(
                "End Speed (mm\u00b3/s)",
                value=20.0,
                min_value=0.1,
                step=0.5,
                format="%.1f",
            )
        with col3:
            flow_step = st.number_input(
                "Step (mm\u00b3/s)",
                value=0.5,
                min_value=0.1,
                step=0.5,
                format="%.1f",
            )

        col4, col5, col6 = st.columns(3)
        with col4:
            flow_nozzle_temp = st.number_input(
                "Nozzle Temp (\u00b0C)",
                min_value=150,
                max_value=350,
                key="flow_nozzle_temp",
            )
        with col5:
            flow_bed_temp = st.number_input(
                "Bed Temp (\u00b0C)",
                min_value=0,
                max_value=150,
                key="flow_bed_temp",
            )
        with col6:
            flow_fan = st.number_input(
                "Fan Speed (%)",
                min_value=0,
                max_value=100,
                key="flow_fan",
            )

        with st.expander("Advanced Slicer Settings"):
            flow_level_height = st.number_input(
                "Level Height (mm)",
                value=1.0,
                min_value=0.2,
                step=0.5,
                key="flow_level_height",
            )
            flow_layer_height = st.number_input(
                "Layer Height (mm)",
                min_value=0.05,
                max_value=1.0,
                format="%.2f",
                key="flow_lh",
            )
            flow_extrusion_width = st.number_input(
                "Extrusion Width (mm)",
                min_value=0.1,
                max_value=2.0,
                format="%.2f",
                key="flow_ew",
            )

        # Level count preview
        if end_speed > start_speed and flow_step > 0:
            num_levels = round((end_speed - start_speed) / flow_step) + 1
            st.info(
                f"{num_levels} levels: "
                f"{start_speed:.1f} \u2192 {end_speed:.1f} mm\u00b3/s"
            )

        if st.button("Generate Flow Specimen", type="primary",
                      key="run_flow"):
            _temp_err = _check_printer_temps(
                printer, flow_nozzle_temp, flow_bed_temp,
            )
            if _temp_err:
                st.error(_temp_err)
                st.stop()
            run_dir = _fresh_output_dir(custom_output_dir)
            args = build_flow_namespace(
                filament_type=filament_type,
                start_speed=start_speed,
                end_speed=end_speed,
                step=flow_step,
                level_height=flow_level_height,
                nozzle_temp=flow_nozzle_temp,
                bed_temp=flow_bed_temp,
                fan_speed=flow_fan,
                nozzle_size=nozzle_size,
                nozzle_high_flow=nozzle_high_flow,
                nozzle_hardened=nozzle_hardened,
                layer_height=flow_layer_height,
                extrusion_width=flow_extrusion_width,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=None,
                api_key=None,
                no_upload=True,
                print_after_upload=False,
            )
            with st.spinner("Running volumetric flow pipeline..."):
                success, log = run_pipeline(flow_run, args)
            st.session_state["_last_run"] = {
                "output_dir": run_dir,
                "ascii_gcode": ascii_gcode,
                "success": success,
                "log": log,
                "tab": "flow",
                "upload_enabled": enable_upload,
                "printer_url": printer_url,
                "api_key": api_key,
            }
            st.session_state.pop("_upload_status", None)
            st.session_state.pop("_upload_message", None)
            st.session_state.pop("_print_after", None)
            st.session_state.pop("upload_print_after", None)

        _run = st.session_state.get("_last_run")
        if _run and _run["tab"] == "flow":
            _show_results(st, _run)

    # === Tab 4: Pressure Advance ===
    with tab_pa:
        st.subheader("Pressure Advance")
        pa_method = st.radio(
            "Method",
            options=["Tower", "Pattern"],
            horizontal=True,
            help=(
                "Tower: hollow rectangular tower with PA by height. "
                "Pattern: nested chevron (V-shape) outlines with PA by X position."
            ),
        )
        method_key = pa_method.lower()

        if method_key == "tower":
            st.caption(
                "Generate a hollow rectangular tower with sharp corners. "
                "PA value increases with height."
            )
        else:
            st.caption(
                "Generate nested chevron (V-shape) outlines in a frame "
                "with embossed PA labels. Each chevron has a different PA "
                "value \u2014 inspect which has the sharpest corners."
            )

        col1, col2, col3 = st.columns(3)
        with col1:
            start_pa = st.number_input(
                "Start PA",
                value=0.0,
                min_value=0.0,
                step=0.005,
                format="%.4f",
            )
        with col2:
            end_pa = st.number_input(
                "End PA",
                value=0.10,
                min_value=0.0,
                step=0.005,
                format="%.4f",
            )
        with col3:
            pa_step_val = st.number_input(
                "PA Step",
                value=0.005,
                min_value=0.001,
                step=0.001,
                format="%.4f",
            )

        col4, col5, col6 = st.columns(3)
        with col4:
            pa_nozzle_temp = st.number_input(
                "Nozzle Temp (\u00b0C)",
                min_value=150,
                max_value=350,
                key="pa_nozzle_temp",
            )
        with col5:
            pa_bed_temp = st.number_input(
                "Bed Temp (\u00b0C)",
                min_value=0,
                max_value=150,
                key="pa_bed_temp",
            )
        with col6:
            pa_fan = st.number_input(
                "Fan Speed (%)",
                min_value=0,
                max_value=100,
                key="pa_fan",
            )

        # Pattern-specific settings (defaults used when method is tower)
        pa_corner_angle = 90.0
        pa_arm_length = 40.0
        pa_wall_count = 3
        pa_num_layers = 4
        pa_frame_layers = 1
        pa_pattern_spacing = 1.6
        pa_frame_offset = 0.0
        if method_key == "pattern":
            with st.expander("Pattern Settings"):
                pa_corner_angle = st.number_input(
                    "Corner Angle (\u00b0)",
                    value=90.0,
                    min_value=10.0,
                    max_value=170.0,
                    step=5.0,
                    key="pa_corner_angle",
                )
                pa_arm_length = st.number_input(
                    "Arm Length (mm)",
                    value=40.0,
                    min_value=5.0,
                    step=5.0,
                    key="pa_arm_length",
                )
                pa_wall_count = st.number_input(
                    "Wall Count",
                    value=3,
                    min_value=1,
                    max_value=10,
                    key="pa_wall_count",
                )
                pa_num_layers = st.number_input(
                    "Number of Layers",
                    value=4,
                    min_value=1,
                    max_value=20,
                    key="pa_num_layers",
                )
                pa_frame_layers = st.number_input(
                    "Frame Layers",
                    value=1,
                    min_value=1,
                    max_value=10,
                    key="pa_frame_layers",
                )
                pa_pattern_spacing = st.number_input(
                    "Pattern Spacing (mm)",
                    value=1.6,
                    min_value=0.0,
                    step=0.5,
                    key="pa_pattern_spacing",
                )
                pa_frame_offset = st.number_input(
                    "Frame Offset (mm)",
                    value=0.0,
                    min_value=0.0,
                    step=0.5,
                    key="pa_frame_offset",
                )

        pa_level_height = 1.0
        with st.expander("Advanced Slicer Settings"):
            if method_key == "tower":
                pa_level_height = st.number_input(
                    "Level Height (mm)",
                    value=1.0,
                    min_value=0.2,
                    step=0.5,
                    key="pa_level_height",
                )
            pa_layer_height = st.number_input(
                "Layer Height (mm)",
                min_value=0.05,
                max_value=1.0,
                format="%.2f",
                key="pa_lh",
            )
            pa_extrusion_width = st.number_input(
                "Extrusion Width (mm)",
                min_value=0.1,
                max_value=2.0,
                format="%.2f",
                key="pa_ew",
            )

        # Level count preview
        if end_pa > start_pa and pa_step_val > 0:
            num_levels = round((end_pa - start_pa) / pa_step_val) + 1
            label = "levels" if method_key == "tower" else "patterns"
            st.info(
                f"{num_levels} {label}: "
                f"PA {start_pa:.4f} \u2192 {end_pa:.4f}"
            )

        if st.button("Generate PA Calibration", type="primary",
                      key="run_pa"):
            _temp_err = _check_printer_temps(
                printer, pa_nozzle_temp, pa_bed_temp,
            )
            if _temp_err:
                st.error(_temp_err)
                st.stop()
            run_dir = _fresh_output_dir(custom_output_dir)
            args = build_pa_namespace(
                filament_type=filament_type,
                start_pa=start_pa,
                end_pa=end_pa,
                pa_step=pa_step_val,
                method=method_key,
                level_height=pa_level_height,
                nozzle_temp=pa_nozzle_temp,
                bed_temp=pa_bed_temp,
                fan_speed=pa_fan,
                nozzle_size=nozzle_size,
                nozzle_high_flow=nozzle_high_flow,
                nozzle_hardened=nozzle_hardened,
                layer_height=pa_layer_height,
                extrusion_width=pa_extrusion_width,
                corner_angle=pa_corner_angle,
                arm_length=pa_arm_length,
                wall_count=pa_wall_count,
                num_layers=pa_num_layers,
                frame_layers=pa_frame_layers,
                pattern_spacing=pa_pattern_spacing,
                frame_offset=pa_frame_offset,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=None,
                api_key=None,
                no_upload=True,
                print_after_upload=False,
            )
            with st.spinner("Running pressure advance pipeline..."):
                success, log = run_pipeline(pa_run, args)
            st.session_state["_last_run"] = {
                "output_dir": run_dir,
                "ascii_gcode": ascii_gcode,
                "success": success,
                "log": log,
                "tab": "pa",
                "upload_enabled": enable_upload,
                "printer_url": printer_url,
                "api_key": api_key,
            }
            st.session_state.pop("_upload_status", None)
            st.session_state.pop("_upload_message", None)
            st.session_state.pop("_print_after", None)
            st.session_state.pop("upload_print_after", None)

        _run = st.session_state.get("_last_run")
        if _run and _run["tab"] == "pa":
            _show_results(st, _run)

    # === Tab 5: Retraction Test ===
    with tab_retraction:
        st.subheader("Retraction Test")
        st.caption(
            "Generate two cylindrical towers spaced apart. Travel moves "
            "between them trigger retraction. Retraction length changes "
            "at each height level so you can inspect stringing."
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            start_retraction = st.number_input(
                "Start Retraction (mm)",
                value=0.0,
                min_value=0.0,
                step=0.1,
                format="%.1f",
            )
        with col2:
            end_retraction = st.number_input(
                "End Retraction (mm)",
                value=2.0,
                min_value=0.0,
                step=0.1,
                format="%.1f",
            )
        with col3:
            retraction_step_val = st.number_input(
                "Step (mm)",
                value=0.1,
                min_value=0.01,
                step=0.1,
                format="%.2f",
            )

        col4, col5, col6 = st.columns(3)
        with col4:
            retraction_nozzle_temp = st.number_input(
                "Nozzle Temp (\u00b0C)",
                min_value=150,
                max_value=350,
                key="retraction_nozzle_temp",
            )
        with col5:
            retraction_bed_temp = st.number_input(
                "Bed Temp (\u00b0C)",
                min_value=0,
                max_value=150,
                key="retraction_bed_temp",
            )
        with col6:
            retraction_fan = st.number_input(
                "Fan Speed (%)",
                min_value=0,
                max_value=100,
                key="retraction_fan",
            )

        retraction_level_height = 1.0
        with st.expander("Advanced Slicer Settings"):
            retraction_level_height = st.number_input(
                "Level Height (mm)",
                value=1.0,
                min_value=0.2,
                step=0.5,
                key="retraction_level_height",
            )
            retraction_layer_height = st.number_input(
                "Layer Height (mm)",
                min_value=0.05,
                max_value=1.0,
                format="%.2f",
                key="retraction_lh",
            )
            retraction_extrusion_width = st.number_input(
                "Extrusion Width (mm)",
                min_value=0.1,
                max_value=2.0,
                format="%.2f",
                key="retraction_ew",
            )

        # Level count preview
        if end_retraction > start_retraction and retraction_step_val > 0:
            num_levels = (
                round((end_retraction - start_retraction) / retraction_step_val)
                + 1
            )
            st.info(
                f"{num_levels} levels: "
                f"{start_retraction:.1f} \u2192 {end_retraction:.1f} mm"
            )

        if st.button("Generate Retraction Test", type="primary",
                      key="run_retraction"):
            _temp_err = _check_printer_temps(
                printer, retraction_nozzle_temp, retraction_bed_temp,
            )
            if _temp_err:
                st.error(_temp_err)
                st.stop()
            run_dir = _fresh_output_dir(custom_output_dir)
            args = build_retraction_namespace(
                filament_type=filament_type,
                start_retraction=start_retraction,
                end_retraction=end_retraction,
                retraction_step=retraction_step_val,
                level_height=retraction_level_height,
                nozzle_temp=retraction_nozzle_temp,
                bed_temp=retraction_bed_temp,
                fan_speed=retraction_fan,
                nozzle_size=nozzle_size,
                nozzle_high_flow=nozzle_high_flow,
                nozzle_hardened=nozzle_hardened,
                layer_height=retraction_layer_height,
                extrusion_width=retraction_extrusion_width,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=None,
                api_key=None,
                no_upload=True,
                print_after_upload=False,
            )
            with st.spinner("Running retraction test pipeline..."):
                success, log = run_pipeline(retraction_run, args)
            st.session_state["_last_run"] = {
                "output_dir": run_dir,
                "ascii_gcode": ascii_gcode,
                "success": success,
                "log": log,
                "tab": "retraction",
                "upload_enabled": enable_upload,
                "printer_url": printer_url,
                "api_key": api_key,
            }
            st.session_state.pop("_upload_status", None)
            st.session_state.pop("_upload_message", None)
            st.session_state.pop("_print_after", None)
            st.session_state.pop("upload_print_after", None)

        _run = st.session_state.get("_last_run")
        if _run and _run["tab"] == "retraction":
            _show_results(st, _run)

    # === Tab 6: Shrinkage ===
    with tab_shrinkage:
        st.subheader("Shrinkage Test")
        st.caption(
            "Generate a 3-axis calibration cross. Print it, measure each "
            "arm with calipers, and calculate: "
            "shrinkage = (nominal \u2212 measured) / nominal \u00d7 100."
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            shrinkage_nozzle_temp = st.number_input(
                "Nozzle Temp (\u00b0C)",
                min_value=150,
                max_value=350,
                key="shrinkage_nozzle_temp",
            )
        with col2:
            shrinkage_bed_temp = st.number_input(
                "Bed Temp (\u00b0C)",
                min_value=0,
                max_value=150,
                key="shrinkage_bed_temp",
            )
        with col3:
            shrinkage_fan = st.number_input(
                "Fan Speed (%)",
                min_value=0,
                max_value=100,
                key="shrinkage_fan",
            )

        with st.expander("Advanced Slicer Settings"):
            shrinkage_arm_length = st.number_input(
                "Arm Length (mm)",
                value=100.0,
                min_value=20.0,
                max_value=200.0,
                step=10.0,
                key="shrinkage_arm_length",
            )
            shrinkage_layer_height = st.number_input(
                "Layer Height (mm)",
                min_value=0.05,
                max_value=1.0,
                format="%.2f",
                key="shrinkage_lh",
            )
            shrinkage_extrusion_width = st.number_input(
                "Extrusion Width (mm)",
                min_value=0.1,
                max_value=2.0,
                format="%.2f",
                key="shrinkage_ew",
            )

        st.info(
            f"Expected dimensions: X={shrinkage_arm_length:.1f}  "
            f"Y={shrinkage_arm_length:.1f}  "
            f"Z={shrinkage_arm_length:.1f} mm"
        )

        if st.button("Generate Shrinkage Cross", type="primary",
                      key="run_shrinkage"):
            _temp_err = _check_printer_temps(
                printer, shrinkage_nozzle_temp, shrinkage_bed_temp,
            )
            if _temp_err:
                st.error(_temp_err)
                st.stop()
            run_dir = _fresh_output_dir(custom_output_dir)
            args = build_shrinkage_namespace(
                filament_type=filament_type,
                arm_length=shrinkage_arm_length,
                nozzle_temp=shrinkage_nozzle_temp,
                bed_temp=shrinkage_bed_temp,
                fan_speed=shrinkage_fan,
                nozzle_size=nozzle_size,
                nozzle_high_flow=nozzle_high_flow,
                nozzle_hardened=nozzle_hardened,
                layer_height=shrinkage_layer_height,
                extrusion_width=shrinkage_extrusion_width,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=None,
                api_key=None,
                no_upload=True,
                print_after_upload=False,
            )
            with st.spinner("Running shrinkage test pipeline..."):
                success, log = run_pipeline(shrinkage_run, args)
            st.session_state["_last_run"] = {
                "output_dir": run_dir,
                "ascii_gcode": ascii_gcode,
                "success": success,
                "log": log,
                "tab": "shrinkage",
                "upload_enabled": enable_upload,
                "printer_url": printer_url,
                "api_key": api_key,
            }
            st.session_state.pop("_upload_status", None)
            st.session_state.pop("_upload_message", None)
            st.session_state.pop("_print_after", None)
            st.session_state.pop("upload_print_after", None)

        _run = st.session_state.get("_last_run")
        if _run and _run["tab"] == "shrinkage":
            _show_results(st, _run)

    # === Tab 7: Calibration Results ===
    with tab_results:
        st.subheader("Calibration Results")
        st.markdown(
            "Record your calibration results and merge them into "
            "a PrusaSlicer config."
        )

        # Temperature result
        set_temp = st.checkbox(
            "Set nozzle temperature", key="res_set_temp",
        )
        res_temp = st.number_input(
            "Temperature (°C)", 150, 350, preset["hotend"],
            disabled=not set_temp, key="res_temp",
        )

        # Volumetric flow result
        set_flow = st.checkbox(
            "Set max volumetric speed", key="res_set_flow",
        )
        res_flow = st.number_input(
            "Max volumetric speed (mm³/s)", 0.5, 50.0, 11.0,
            step=0.5, disabled=not set_flow, key="res_flow",
        )

        # Pressure advance result
        set_pa = st.checkbox(
            "Set pressure advance", key="res_set_pa",
        )
        res_pa = st.number_input(
            "PA value", 0.0000, 2.0000, 0.0400,
            step=0.005, format="%.4f",
            disabled=not set_pa, key="res_pa",
        )

        # Extrusion multiplier result
        set_em = st.checkbox(
            "Set extrusion multiplier", key="res_set_em",
        )
        res_em = st.number_input(
            "Extrusion multiplier", 0.50, 1.50, 1.00,
            step=0.01, format="%.2f",
            disabled=not set_em, key="res_em",
        )

        # Retraction length result
        set_retraction = st.checkbox(
            "Set retraction length", key="res_set_retraction",
        )
        res_retraction = st.number_input(
            "Retraction length (mm)", 0.0, 10.0, 0.8,
            step=0.1, format="%.1f",
            disabled=not set_retraction, key="res_retraction",
        )

        # Build results object
        results = build_calibration_results(
            set_temp=set_temp, temperature=int(res_temp),
            set_flow=set_flow, max_volumetric_speed=float(res_flow),
            set_pa=set_pa, pa_value=float(res_pa),
            set_em=set_em, extrusion_multiplier=float(res_em),
            set_retraction=set_retraction,
            retraction_length=float(res_retraction),
            printer=printer,
        )

        # Show change summary
        has_any = (
            results.temperature is not None
            or results.max_volumetric_speed is not None
            or results.pa_value is not None
            or results.extrusion_multiplier is not None
            or results.retraction_length is not None
        )
        if has_any:
            summary = build_change_summary(results)
            st.markdown("### Changes")
            st.markdown(summary)

        # Merge & download (only if a config.ini is loaded)
        config_ini_path = st.session_state.get("config_ini", "")
        if has_any and config_ini_path and Path(config_ini_path).is_file():
            ini_text = Path(config_ini_path).read_text(
                encoding="utf-8", errors="replace",
            )
            merged = merge_results_into_ini(ini_text, results)
            ini_name = Path(config_ini_path).stem + "_calibrated.ini"
            st.download_button(
                label=f"Download {ini_name}",
                data=merged.encode("utf-8"),
                file_name=ini_name,
                mime="text/plain",
            )
        elif has_any and not config_ini_path:
            st.info(
                "Load a PrusaSlicer config.ini in the sidebar to "
                "merge results and download."
            )


def _show_results(
    st: Any,
    run_info: Dict[str, Any],
) -> None:  # pragma: no cover
    """Display pipeline results: status, download, thumbnail, upload, log."""
    output_dir = run_info["output_dir"]
    ascii_gcode = run_info["ascii_gcode"]
    success = run_info["success"]
    log = run_info["log"]

    if success:
        st.success("Pipeline completed!")
    else:
        st.error("Pipeline failed!")

    # Download button
    gcode_path = find_output_file(output_dir, ascii_gcode)
    if gcode_path is not None:
        with open(gcode_path, "rb") as fh:
            st.download_button(
                label=f"Download {gcode_path.name}",
                data=fh.read(),
                file_name=gcode_path.name,
                mime="application/octet-stream",
            )

    # Thumbnail preview (use most recent STL for shared output dirs).
    # Cache the rendered PNG in session state so the media-file ID stays
    # stable across Streamlit reruns (avoids "Missing file" errors).
    stl_files = list(Path(output_dir).glob("*.stl"))
    if stl_files:
        newest_stl = max(stl_files, key=lambda f: f.stat().st_mtime)
        stl_key = str(newest_stl)
        cached = st.session_state.get("_thumbnail_stl")
        if cached == stl_key:
            png_data = st.session_state.get("_thumbnail_png")
        else:
            try:
                png_data = gl.render_stl_to_png(str(newest_stl), 440, 248)
                st.session_state["_thumbnail_stl"] = stl_key
                st.session_state["_thumbnail_png"] = png_data
            except Exception:
                png_data = None
        if png_data is not None:
            st.image(png_data, caption="Model Preview", width=440)

    # Upload section (only when pipeline succeeded and upload is configured)
    if (
        success
        and run_info.get("upload_enabled")
        and gcode_path is not None
    ):
        _show_upload_section(st, run_info, gcode_path)

    # Pipeline log
    with st.expander("Pipeline Log", expanded=not success):
        st.code(log)


def _show_upload_section(
    st: Any,
    run_info: Dict[str, Any],
    gcode_path: Path,
) -> None:  # pragma: no cover
    """Show upload confirmation, progress, and result."""
    upload_status = st.session_state.get("_upload_status")

    with st.container(border=True):
        st.subheader("\U0001f4e4 Upload to Printer")

        if upload_status is None:
            # --- Confirmation step ---
            file_size_mb = gcode_path.stat().st_size / (1024 * 1024)
            st.markdown(
                f"**Printer:** `{run_info['printer_url']}`  \n"
                f"**File:** `{gcode_path.name}`  \n"
                f"**Size:** {file_size_mb:.1f} MB"
            )
            print_after = st.checkbox(
                "Print after upload", value=False,
                key="upload_print_after",
            )
            col_up, col_skip, _pad = st.columns([1, 1, 4])
            with col_up:
                if st.button(
                    "Upload", type="primary", key="do_upload",
                ):
                    st.session_state["_print_after"] = print_after
                    st.session_state["_upload_status"] = "uploading"
                    st.rerun()
            with col_skip:
                if st.button("Skip", key="skip_upload"):
                    st.session_state["_upload_status"] = "skipped"
                    st.rerun()

        elif upload_status == "uploading":
            # --- Upload in progress ---
            with st.spinner("Uploading to printer\u2026"):
                ok, msg = upload_to_printer(
                    printer_url=run_info["printer_url"],
                    api_key=run_info["api_key"],
                    gcode_path=str(gcode_path),
                    print_after_upload=st.session_state.get(
                        "_print_after", False
                    ),
                )
            if ok:
                st.session_state["_upload_status"] = "success"
                st.session_state["_upload_message"] = msg
            else:
                st.session_state["_upload_status"] = "failed"
                st.session_state["_upload_message"] = msg
            st.rerun()

        elif upload_status == "success":
            st.success(
                st.session_state.get("_upload_message", "Uploaded!")
            )

        elif upload_status == "failed":
            st.error(
                st.session_state.get(
                    "_upload_message", "Upload failed."
                )
            )
            if st.button("Retry Upload", key="retry_upload"):
                st.session_state["_upload_status"] = "uploading"
                st.rerun()

        elif upload_status == "skipped":
            st.info("Upload skipped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    """Launch the Streamlit GUI."""
    import os
    import sys

    from streamlit.web.cli import main as st_main

    script_path = os.path.abspath(__file__)
    sys.argv = ["streamlit", "run", script_path,
                "--server.headless", "true"]
    st_main()


if __name__ == "__main__":  # pragma: no cover
    _app()
