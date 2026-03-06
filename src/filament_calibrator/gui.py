"""Streamlit GUI for filament calibration tools.

Provides a browser-based interface to the temperature-tower,
volumetric-flow, and pressure-advance CLI pipelines.  All heavy
lifting (CAD, slicing, G-code processing) runs server-side.
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
from filament_calibrator.ini_parser import parse_prusaslicer_ini
from filament_calibrator.printer_gcode import KNOWN_PRINTERS


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

_PRINTER_LIST: List[str] = sorted(KNOWN_PRINTERS)


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
    firmware: str,
    method: str = "tower",
    level_height: float = 1.0,
    nozzle_temp: int,
    bed_temp: int,
    fan_speed: int,
    nozzle_size: float,
    layer_height: float,
    extrusion_width: float,
    corner_angle: float = 90.0,
    arm_length: float = 40.0,
    wall_count: int = 3,
    num_layers: int = 4,
    pattern_spacing: float = 1.6,
    frame_offset: float = 3.0,
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
        firmware=firmware,
        method=method,
        level_height=level_height,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        fan_speed=fan_speed,
        nozzle_size=nozzle_size,
        layer_height=layer_height,
        extrusion_width=extrusion_width,
        corner_angle=corner_angle,
        arm_length=arm_length,
        wall_count=wall_count,
        num_layers=num_layers,
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
    """Find the final G-code file in *output_dir* (not the ``_raw`` one)."""
    ext = ".gcode" if ascii_gcode else ".bgcode"
    candidates = [
        f for f in Path(output_dir).glob(f"*{ext}")
        if "_raw" not in f.name
    ]
    return candidates[0] if candidates else None


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
# INI auto-populate helpers
# ---------------------------------------------------------------------------


def snap_nozzle_size(diameter: float) -> float:
    """Snap *diameter* to the nearest value in :data:`_NOZZLE_SIZES`."""
    return min(_NOZZLE_SIZES, key=lambda s: abs(s - diameter))


def apply_ini_to_session(
    state: Dict[str, Any],
    ini_vals: Dict[str, Any],
) -> None:
    """Write parsed ``.ini`` values into Streamlit session-state widget keys.

    Must be called **before** widgets render so that Streamlit picks up
    the updated values.  Only keys present in *ini_vals* are written.
    """
    if "nozzle_temp" in ini_vals:
        nt = ini_vals["nozzle_temp"]
        state["flow_nozzle_temp"] = nt
        state["pa_nozzle_temp"] = nt

    if "bed_temp" in ini_vals:
        bt = ini_vals["bed_temp"]
        state["tt_bed_temp"] = bt
        state["flow_bed_temp"] = bt
        state["pa_bed_temp"] = bt

    if "fan_speed" in ini_vals:
        fs = ini_vals["fan_speed"]
        state["tt_fan"] = fs
        state["flow_fan"] = fs
        state["pa_fan"] = fs

    if "layer_height" in ini_vals:
        lh = ini_vals["layer_height"]
        state["flow_lh"] = lh
        state["pa_lh"] = lh

    if "extrusion_width" in ini_vals:
        ew = ini_vals["extrusion_width"]
        state["flow_ew"] = ew
        state["pa_ew"] = ew

    if "nozzle_diameter" in ini_vals:
        snapped = snap_nozzle_size(ini_vals["nozzle_diameter"])
        if snapped in _NOZZLE_SIZES:
            state["_ini_nozzle_size"] = snapped

    if "printer_model" in ini_vals:
        pm = ini_vals["printer_model"].upper()
        if pm in _PRINTER_LIST:
            state["_ini_printer"] = pm

    if "bed_center" in ini_vals:
        state["_ini_bed_center"] = ini_vals["bed_center"]

    if "filament_type" in ini_vals:
        ft = ini_vals["filament_type"].upper()
        if ft in _KNOWN_TYPES:
            state["_ini_filament_type"] = ft


# ---------------------------------------------------------------------------
# Streamlit app (only imported when actually running the GUI)
# ---------------------------------------------------------------------------

def _app() -> None:  # pragma: no cover
    """Main Streamlit application."""
    import streamlit as st

    from filament_calibrator.cli import run as temp_run
    from filament_calibrator.flow_cli import run as flow_run
    from filament_calibrator.pa_cli import run as pa_run

    st.set_page_config(
        page_title="Filament Calibrator",
        layout="wide",
    )
    st.title("Filament Calibrator")

    # Apply pending browse-dialog results before widgets render.
    for _key in ("config_ini", "prusaslicer_path", "output_dir"):
        _pending = f"_pending_{_key}"
        if _pending in st.session_state:
            st.session_state[_key] = st.session_state.pop(_pending)

    # Parse .ini and auto-populate fields when the path changes.
    _cur_ini = st.session_state.get("config_ini", "")
    _prev_ini = st.session_state.get("_prev_config_ini", "")
    if _cur_ini != _prev_ini:
        st.session_state["_prev_config_ini"] = _cur_ini
        if _cur_ini and Path(_cur_ini).is_file():
            try:
                ini_vals = parse_prusaslicer_ini(_cur_ini)
            except Exception:
                ini_vals = {}
            if ini_vals:
                apply_ini_to_session(st.session_state, ini_vals)

    # --- Sidebar: shared settings ---
    with st.sidebar:
        st.header("Common Settings")

        _ini_ft = st.session_state.get("_ini_filament_type")
        _ft_idx = (
            _KNOWN_TYPES.index(_ini_ft)
            if _ini_ft in _KNOWN_TYPES
            else _KNOWN_TYPES.index("PLA")
        )
        filament_type = st.selectbox(
            "Filament Type",
            options=_KNOWN_TYPES,
            index=_ft_idx,
        )
        preset = get_preset(filament_type)

        _ini_pr = st.session_state.get("_ini_printer")
        _pr_idx = (
            _PRINTER_LIST.index(_ini_pr)
            if _ini_pr in _PRINTER_LIST
            else _PRINTER_LIST.index("COREONE")
        )
        printer = st.selectbox(
            "Printer",
            options=_PRINTER_LIST,
            index=_pr_idx,
        )

        _ini_ns = st.session_state.get("_ini_nozzle_size")
        _ns_idx = (
            _NOZZLE_SIZES.index(_ini_ns)
            if _ini_ns in _NOZZLE_SIZES
            else _NOZZLE_SIZES.index(0.4)
        )
        nozzle_size = st.selectbox(
            "Nozzle Size (mm)",
            options=_NOZZLE_SIZES,
            index=_ns_idx,
        )

        ascii_gcode = st.checkbox(
            "ASCII G-code (.gcode)",
            value=False,
            help="Default is binary (.bgcode) with thumbnail previews",
        )

        st.divider()
        st.subheader("PrusaLink Upload")
        enable_upload = st.checkbox("Upload to printer", value=False)
        printer_url = ""
        api_key = ""
        print_after = False
        if enable_upload:
            printer_url = st.text_input(
                "Printer URL",
                placeholder="http://192.168.1.100",
            )
            api_key = st.text_input("API Key", type="password")
            print_after = st.checkbox("Print after upload", value=False)

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

    # Set default session-state values for keyed widgets.  Only sets the
    # value when the key is NEW (first render).  This avoids the Streamlit
    # warning that fires when both ``value=`` and a session-state key
    # are provided to the same widget.
    _widget_defaults = {
        "tt_bed_temp": preset["bed"],
        "tt_fan": preset["fan"],
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
    }
    for _wk, _wv in _widget_defaults.items():
        if _wk not in st.session_state:
            st.session_state[_wk] = _wv

    # --- Tabs ---
    tab_temp, tab_flow, tab_pa = st.tabs([
        "Temperature Tower", "Volumetric Flow", "Pressure Advance",
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
                value=preset["temp_max"],
                min_value=150,
                max_value=350,
                step=5,
            )
        with col2:
            end_temp = st.number_input(
                "End Temp (\u00b0C) \u2014 top",
                value=preset["temp_min"],
                min_value=150,
                max_value=350,
                step=5,
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
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=printer_url if enable_upload else None,
                api_key=api_key if enable_upload else None,
                no_upload=not enable_upload,
                print_after_upload=print_after,
            )
            with st.spinner("Running temperature tower pipeline..."):
                success, log = run_pipeline(temp_run, args)
            _show_results(st, run_dir, ascii_gcode, success, log)

    # === Tab 2: Volumetric Flow ===
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
                value=1.0,
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
                layer_height=flow_layer_height,
                extrusion_width=flow_extrusion_width,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=printer_url if enable_upload else None,
                api_key=api_key if enable_upload else None,
                no_upload=not enable_upload,
                print_after_upload=print_after,
            )
            with st.spinner("Running volumetric flow pipeline..."):
                success, log = run_pipeline(flow_run, args)
            _show_results(st, run_dir, ascii_gcode, success, log)

    # === Tab 3: Pressure Advance ===
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

        firmware = st.selectbox(
            "Firmware",
            options=["marlin", "klipper"],
            index=0,
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
        pa_pattern_spacing = 1.6
        pa_frame_offset = 3.0
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
                pa_pattern_spacing = st.number_input(
                    "Pattern Spacing (mm)",
                    value=1.6,
                    min_value=0.0,
                    step=0.5,
                    key="pa_pattern_spacing",
                )
                pa_frame_offset = st.number_input(
                    "Frame Offset (mm)",
                    value=3.0,
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
            run_dir = _fresh_output_dir(custom_output_dir)
            args = build_pa_namespace(
                filament_type=filament_type,
                start_pa=start_pa,
                end_pa=end_pa,
                pa_step=pa_step_val,
                firmware=firmware,
                method=method_key,
                level_height=pa_level_height,
                nozzle_temp=pa_nozzle_temp,
                bed_temp=pa_bed_temp,
                fan_speed=pa_fan,
                nozzle_size=nozzle_size,
                layer_height=pa_layer_height,
                extrusion_width=pa_extrusion_width,
                corner_angle=pa_corner_angle,
                arm_length=pa_arm_length,
                wall_count=pa_wall_count,
                num_layers=pa_num_layers,
                pattern_spacing=pa_pattern_spacing,
                frame_offset=pa_frame_offset,
                printer=printer,
                ascii_gcode=ascii_gcode,
                output_dir=run_dir,
                config_ini=config_ini,
                prusaslicer_path=prusaslicer_path,
                printer_url=printer_url if enable_upload else None,
                api_key=api_key if enable_upload else None,
                no_upload=not enable_upload,
                print_after_upload=print_after,
            )
            with st.spinner("Running pressure advance pipeline..."):
                success, log = run_pipeline(pa_run, args)
            _show_results(st, run_dir, ascii_gcode, success, log)


def _show_results(
    st: Any,
    output_dir: str,
    ascii_gcode: bool,
    success: bool,
    log: str,
) -> None:  # pragma: no cover
    """Display pipeline results: status, download, thumbnail, log."""
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

    # Thumbnail preview
    stl_files = list(Path(output_dir).glob("*.stl"))
    if stl_files:
        try:
            from filament_calibrator.thumbnail import render_stl_to_png

            png_data = render_stl_to_png(str(stl_files[0]), 440, 248)
            st.image(png_data, caption="Model Preview", width=440)
        except Exception:
            pass

    # Pipeline log
    with st.expander("Pipeline Log", expanded=not success):
        st.code(log)


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
