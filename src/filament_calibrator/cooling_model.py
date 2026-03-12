"""Parametric single-tower model for cooling/fan-speed calibration.

Generates a single cylindrical tower on a rectangular base plate.  The small
tower diameter makes it sensitive to cooling effects — when printed with
``M106`` fan-speed commands inserted at each height level, the user can
inspect print quality at each height to find the optimal fan speed.

All dimensions are in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_cooling_tower_stl() to avoid
# loading the heavy OCCT/casadi native libraries at module-import time.
cq: Any = None  # populated by _ensure_cq()

# Stub/lazy-import helpers live in _cq_compat; thin wrappers here keep
# existing call sites and test imports working.
from filament_calibrator._cq_compat import ensure_cq as _ensure_cq_impl


def _ensure_cq() -> None:
    """Import cadquery on first use and cache in module globals."""
    global cq  # noqa: PLW0603
    if cq is None:
        cq = _ensure_cq_impl()

# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

TOWER_DIAMETER: float = 15.0
"""Diameter of the cylindrical tower in mm."""

BASE_LENGTH: float = 30.0
"""X dimension of the rectangular base plate in mm."""

BASE_WIDTH: float = 30.0
"""Y dimension of the rectangular base plate in mm."""

BASE_HEIGHT: float = 1.0
"""Height of the base plate in mm (for bed adhesion)."""

LEVEL_HEIGHT: float = 5.0
"""Default height per cooling level in mm."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class CoolingTowerConfig:
    """Parameters for the cooling calibration tower model.

    Attributes
    ----------
    num_levels:     Number of cooling/fan-speed levels.
    level_height:   Height per level in mm.
    tower_diameter: Diameter of the cylindrical tower in mm.
    base_length:    X dimension of the base plate in mm.
    base_width:     Y dimension of the base plate in mm.
    base_height:    Height of the base plate in mm.
    filament_type:  Label for filament type (e.g. ``"PLA"``).
    """
    num_levels: int
    level_height: float = LEVEL_HEIGHT
    tower_diameter: float = TOWER_DIAMETER
    base_length: float = BASE_LENGTH
    base_width: float = BASE_WIDTH
    base_height: float = BASE_HEIGHT
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def total_height(config: CoolingTowerConfig) -> float:
    """Return the total Z height of the model (base + tower levels)."""
    return config.base_height + config.num_levels * config.level_height


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_base(config: CoolingTowerConfig) -> cq.Workplane:
    """Create the rectangular base plate centred at the XY origin."""
    return (
        cq.Workplane("XY")
        .box(
            config.base_length,
            config.base_width,
            config.base_height,
            centered=(True, True, False),
        )
    )


def _make_tower(config: CoolingTowerConfig) -> cq.Workplane:
    """Create the cylindrical tower centred at the XY origin.

    The cylinder is built on the XY plane and translated so that its
    base sits at ``Z = base_height`` (on top of the base plate).
    """
    height = config.num_levels * config.level_height
    radius = config.tower_diameter / 2.0
    return (
        cq.Workplane("XY")
        .circle(radius)
        .extrude(height)
        .translate((0, 0, config.base_height))
    )


def _make_cooling_tower(config: CoolingTowerConfig) -> cq.Workplane:
    """Build the complete cooling tower model: base plate + cylinder."""
    base = _make_base(config)
    tower = _make_tower(config)
    return base.union(tower)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_cooling_tower_stl(
    config: CoolingTowerConfig,
    output_path: str,
) -> str:
    """One-shot: build the cooling tower model and export to STL.

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
    shape = _make_cooling_tower(config)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
