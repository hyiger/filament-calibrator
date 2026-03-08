"""PyInstaller entry point for the Filament Calibrator GUI.

Launches the Streamlit GUI using bootstrap.run() directly,
bypassing the CLI argument parser which breaks in frozen environments.
"""
from __future__ import annotations

import multiprocessing
import os
import sys


def _patch_streamlit_paths() -> None:
    """Fix Streamlit's runtime path detection in frozen environments."""
    if getattr(sys, "frozen", False):
        bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
        os.environ.setdefault(
            "STREAMLIT_STATIC_PATH",
            os.path.join(bundle_dir, "streamlit", "static"),
        )


def main() -> None:
    """Launch the Streamlit GUI."""
    multiprocessing.freeze_support()  # Required on Windows
    _patch_streamlit_paths()

    from streamlit.web.bootstrap import run

    # Resolve the gui.py script path
    if getattr(sys, "frozen", False):
        # Inside PyInstaller bundle
        script_path = os.path.join(
            sys._MEIPASS,  # type: ignore[attr-defined]
            "filament_calibrator",
            "gui.py",
        )
    else:
        # Development / unfrozen
        script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "filament_calibrator",
            "gui.py",
        )

    run(
        script_path,
        is_hello=False,
        args=[],
        flag_options={
            "server.headless": True,
            "browser.gatherUsageStats": False,
        },
    )


if __name__ == "__main__":
    main()
