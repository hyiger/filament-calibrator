# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for FilamentCalibrator GUI.

Build with:  pyinstaller filament-calibrator.spec
Output:      dist/FilamentCalibrator/  (--onedir mode)
"""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

a = Analysis(
    ["gui_entry.py"],
    pathex=[],
    binaries=[],
    datas=[],
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

# Collect data files and binaries for packages with native/static assets.
for pkg in ("streamlit", "cadquery", "OCP", "gcode_lib"):
    try:
        datas, binaries, hiddenimports = collect_all(pkg)
        a.datas += datas
        a.binaries += binaries
        a.hiddenimports += hiddenimports
    except Exception:
        pass  # Package may not be installed

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
