"""Parametric hollow rectangular tower model for pressure advance calibration.

Generates a rectangular box with sharp 90-degree corners, then shells it
to make it hollow.  When printed at high speed, corner quality reveals
the optimal pressure advance (linear advance) value.  All dimensions
are in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_pa_tower_stl() to avoid loading
# the heavy OCCT/casadi native libraries at module-import time.
cq: Any = None  # populated by _ensure_cq()

# Stub/lazy-import helpers live in _cq_compat; thin wrappers here keep
# existing call sites and test imports working.
from filament_calibrator._cq_compat import ensure_cq as _ensure_cq_impl
from filament_calibrator._cq_compat import stub_casadi as _stub_casadi


def _ensure_cq() -> None:
    """Import cadquery on first use and cache in module globals."""
    global cq  # noqa: PLW0603
    if cq is None:
        cq = _ensure_cq_impl()

# ---------------------------------------------------------------------------
# Geometry constants (defaults for the PA tower)
# ---------------------------------------------------------------------------

TOWER_WIDTH = 60.0       # X dimension (mm) — long enough for speed buildup
TOWER_DEPTH = 60.0       # Y dimension (mm)
WALL_THICKNESS = 1.6     # shell wall thickness (mm)
LEVEL_HEIGHT = 1.0       # default height per PA level (mm)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class PATowerConfig:
    """Parameters for the pressure advance test tower.

    Attributes
    ----------
    num_levels:     Number of PA value levels.
    level_height:   Height per level in mm.
    width:          X dimension of the tower.
    depth:          Y dimension of the tower.
    wall_thickness: Shell wall thickness in mm.
    filament_type:  Label for filament type (e.g. ``"PLA"``).
    """
    num_levels: int
    level_height: float = LEVEL_HEIGHT
    width: float = TOWER_WIDTH
    depth: float = TOWER_DEPTH
    wall_thickness: float = WALL_THICKNESS
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def total_height(config: PATowerConfig) -> float:
    """Return the total Z height of the tower."""
    return config.num_levels * config.level_height


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_hollow_tower(config: PATowerConfig, height: float) -> cq.Workplane:
    """Build the hollow rectangular tower.

    Construction:

    1. Create a solid rectangle (width × depth), extrude to *height*.
    2. Cut a smaller inner rectangle to create the hollow shell.

    No fillets are applied — sharp 90-degree corners are the entire
    point of this calibration test.
    """
    outer = (
        cq.Workplane("XY")
        .rect(config.width, config.depth)
        .extrude(height)
    )

    inner_w = config.width - 2 * config.wall_thickness
    inner_d = config.depth - 2 * config.wall_thickness
    inner = (
        cq.Workplane("XY")
        .rect(inner_w, inner_d)
        .extrude(height)
    )

    return outer.cut(inner)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_pa_tower_stl(
    config: PATowerConfig,
    output_path: str,
) -> str:
    """One-shot: build the PA tower and export to STL.

    Parameters
    ----------
    config:      Tower configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    height = total_height(config)
    shape = _make_hollow_tower(config, height)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
