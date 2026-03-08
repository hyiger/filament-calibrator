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


def _patch_streamlit_frozen() -> None:
    """Force Streamlit into production mode inside a PyInstaller bundle.

    Streamlit decides between *production* and *development* mode via the
    ``global.developmentMode`` config option.  Its default is computed by
    checking whether ``"site-packages"`` appears in ``streamlit/config.py``'s
    ``__file__`` path.  In a PyInstaller bundle the path is
    ``_MEIPASS/streamlit/config.py`` — no ``site-packages`` — so the check
    returns ``True`` (dev mode) and Streamlit tries to proxy to a Node dev
    server on port 3000 instead of serving its own static frontend.

    We fix this by:
    1. Forcing ``global.developmentMode`` to ``False`` in the config system.
    2. Patching ``file_util.get_static_dir()`` so the Tornado server finds
       the bundled ``streamlit/static/`` directory.
    """
    if not getattr(sys, "frozen", False):
        return

    bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    static_dir = os.path.join(bundle_dir, "streamlit", "static")

    # 1. Disable development mode so the server serves static files itself.
    try:
        from streamlit import config

        config.set_option(
            "global.developmentMode", False, where_defined="frozen-bundle"
        )
    except Exception:
        pass

    # 2. Point file_util.get_static_dir() at the bundled static directory.
    if os.path.isdir(static_dir):
        try:
            from streamlit import file_util

            file_util.get_static_dir = lambda: static_dir  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            pass


def main() -> None:
    """Launch the Streamlit GUI."""
    multiprocessing.freeze_support()  # Required on Windows
    _patch_frozen_metadata()

    from streamlit.web.bootstrap import run

    _patch_streamlit_frozen()

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
            "global.developmentMode": False,
            "server.headless": True,
            "browser.gatherUsageStats": False,
        },
    )


if __name__ == "__main__":
    main()
