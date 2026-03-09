"""Parametric cube model for extrusion multiplier calibration.

Generates a simple solid cube.  When sliced in vase mode with classic
perimeter walls, the single wall thickness can be measured with calipers
to determine the correct extrusion multiplier.  All dimensions are in
millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_em_cube_stl() to avoid loading
# the heavy OCCT/casadi native libraries at module-import time.
cq: Any = None  # populated by _ensure_cq()


def _stub_casadi() -> None:
    """Provide a stub ``casadi`` package when the real one is not yet loaded.

    cadquery unconditionally imports casadi for its assembly constraint
    solver, but this project uses only basic geometry operations and never
    invokes the solver.  On Windows PyInstaller bundles the casadi native
    DLL (``_casadi.pyd``) is typically missing.  Injecting a lightweight
    stub lets cadquery import cleanly.
    """
    import sys

    if "casadi" not in sys.modules:
        import types

        _fake = types.ModuleType("casadi")
        _fake.__path__ = []  # type: ignore[attr-defined]
        sys.modules["casadi"] = _fake
        sys.modules["casadi.casadi"] = _fake


def _ensure_cq() -> None:
    """Import cadquery on first use and cache in module globals."""
    global cq  # noqa: PLW0603
    if cq is None:
        _stub_casadi()
        import cadquery as _cq

        cq = _cq

# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

CUBE_SIZE = 40.0  # mm — side length of the calibration cube


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class EMCubeConfig:
    """Parameters for the extrusion multiplier test cube.

    Attributes
    ----------
    size:           Side length of the cube in mm.
    filament_type:  Label for filament type (e.g. ``"PLA"``).
    """
    size: float = CUBE_SIZE
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_cube(config: EMCubeConfig) -> cq.Workplane:
    """Build a solid cube centred at the XY origin."""
    return (
        cq.Workplane("XY")
        .rect(config.size, config.size)
        .extrude(config.size)
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_em_cube_stl(
    config: EMCubeConfig,
    output_path: str,
) -> str:
    """One-shot: build the EM cube and export to STL.

    Parameters
    ----------
    config:      Cube configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    shape = _make_cube(config)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
