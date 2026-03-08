# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for FilamentCalibrator GUI.

Build with:  pyinstaller filament-calibrator.spec
Output:      dist/FilamentCalibrator/  (--onedir mode)
"""

from PyInstaller.utils.hooks import collect_all, copy_metadata

block_cipher = None

a = Analysis(
    ["gui_entry.py"],
    pathex=[],
    binaries=[],
    datas=[
        # Streamlit needs the raw .py source to compile and execute.
        # PyInstaller compiles modules to .pyc in the PYZ archive, so we
        # must include gui.py as a data file for Streamlit to find it.
        ("../src/filament_calibrator/gui.py", "filament_calibrator"),
    ],
    hiddenimports=[
        # --- filament_calibrator package ---
        "filament_calibrator",
        "filament_calibrator.gui",
        "filament_calibrator.cli",
        "filament_calibrator.config",
        "filament_calibrator.model",
        "filament_calibrator.slicer",
        "filament_calibrator.tempinsert",
        "filament_calibrator.em_cli",
        "filament_calibrator.em_model",
        "filament_calibrator.flow_cli",
        "filament_calibrator.flow_model",
        "filament_calibrator.flow_insert",
        "filament_calibrator.pa_cli",
        "filament_calibrator.pa_model",
        "filament_calibrator.pa_pattern",
        "filament_calibrator.pa_insert",
        "filament_calibrator.retraction_cli",
        "filament_calibrator.retraction_model",
        "filament_calibrator.retraction_insert",
        "filament_calibrator.shrinkage_cli",
        "filament_calibrator.shrinkage_model",
        "filament_calibrator.ini_writer",
        # --- external ---
        "gcode_lib",
        "streamlit",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Normalize TOC entries to 3-tuples for PyInstaller 6.x compatibility.
# collect_all() / copy_metadata() return 2-tuples (src_path, dest_dir).
# COLLECT expects 3-tuples (dest_name, src_path, typecode) where
# dest_name is the relative path inside the bundle.
import os

def _to_3_tuples(entries, typecode):
    result = []
    for entry in entries:
        if len(entry) == 3:
            result.append(entry)
        elif len(entry) == 2:
            src_path, dest_dir = entry
            if os.path.isdir(src_path):
                # Walk directories (e.g. .dist-info from copy_metadata)
                for root, _dirs, files in os.walk(src_path):
                    for f in files:
                        src_file = os.path.join(root, f)
                        rel = os.path.relpath(src_file, os.path.dirname(src_path))
                        result.append((rel, src_file, typecode))
            else:
                dest_name = os.path.join(dest_dir, os.path.basename(src_path))
                result.append((dest_name, src_path, typecode))
    return result


# Collect data files and binaries for packages with native/static assets.
for pkg in ("streamlit", "cadquery", "OCP", "gcode_lib"):
    try:
        datas, binaries, hiddenimports = collect_all(pkg)
        a.datas += _to_3_tuples(datas, "DATA")
        a.binaries += _to_3_tuples(binaries, "BINARY")
        a.hiddenimports += hiddenimports
    except Exception:
        pass  # Package may not be installed

# Include package metadata (.dist-info) for packages that use
# importlib.metadata at runtime (e.g. streamlit reads its own version).
# The runtime fallback in gui_entry.py handles the case where metadata
# still isn't found (e.g. editable installs in CI).
for pkg in ("streamlit", "filament-calibrator", "gcode-lib"):
    try:
        a.datas += _to_3_tuples(copy_metadata(pkg), "DATA")
    except Exception:
        pass

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # --onedir mode
    name="FilamentCalibrator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console for Streamlit URL output
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FilamentCalibrator",
)
