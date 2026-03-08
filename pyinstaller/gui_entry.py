"""PyInstaller entry point for the Filament Calibrator GUI.

Launches the Streamlit GUI using bootstrap.run() directly,
bypassing the CLI argument parser which breaks in frozen environments.
"""
from __future__ import annotations

import multiprocessing
import os
import sys


def _patch_frozen_metadata() -> None:
    """Make importlib.metadata work in frozen PyInstaller environments.

    PyInstaller bundles .dist-info directories inside _MEIPASS, but
    importlib.metadata may not find them if the path isn't on the search
    list.  We patch ``importlib.metadata.version()`` to fall back to
    scanning _MEIPASS for ``<normalised>-*.dist-info/METADATA`` when the
    standard lookup fails.
    """
    if not getattr(sys, "frozen", False):
        return

    import importlib.metadata as _meta
    from pathlib import Path

    bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    _orig_version = _meta.version

    def _frozen_version(name: str) -> str:
        try:
            return _orig_version(name)
        except _meta.PackageNotFoundError:
            pass
        # Normalise package name (PEP 503) and search _MEIPASS
        normalised = name.lower().replace("-", "_")
        for dist_info in bundle_dir.glob(f"{normalised}-*.dist-info"):
            meta_file = dist_info / "METADATA"
            if meta_file.is_file():
                for line in meta_file.read_text().splitlines():
                    if line.lower().startswith("version:"):
                        return line.split(":", 1)[1].strip()
        # In a frozen bundle all packages are intentionally included;
        # return a placeholder version rather than crashing.
        return "0.0.0"

    _meta.version = _frozen_version  # type: ignore[assignment]


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
    _patch_frozen_metadata()
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
