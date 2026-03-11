"""Parametric tolerance test model for dimensional accuracy calibration.

Generates a flat plate with circular through-holes at specified diameters
and a matching row of cylindrical pegs on a thin base.  The user prints
the specimen, measures hole and peg diameters with calipers, and
compares them to the nominal values to determine the printer's
dimensional tolerance and any systematic over/under-extrusion.

All dimensions are in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_tolerance_stl() to avoid
# loading the heavy OCCT/casadi native libraries at module-import time.
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
# Geometry constants
# ---------------------------------------------------------------------------

PLATE_THICKNESS: float = 5.0
"""Z height of the hole plate in mm."""

PEG_HEIGHT: float = 10.0
"""Z height of cylindrical pegs in mm."""

PEG_BASE_HEIGHT: float = 2.0
"""Z height of the thin base under pegs in mm."""

COLUMN_SPACING: float = 20.0
"""X distance between hole/peg centres in mm."""

ROW_SPACING: float = 25.0
"""Y distance between the hole row and peg row centres in mm."""

PLATE_MARGIN: float = 5.0
"""Margin around outermost holes on the plate in mm."""

BASE_HEIGHT: float = 1.0
"""Build plate adhesion layer height in mm."""

DEFAULT_DIAMETERS: tuple[float, ...] = (3.0, 5.0, 8.0, 10.0, 12.0, 15.0)
"""Default test diameters in mm."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class ToleranceTestConfig:
    """Parameters for the tolerance calibration test model.

    Attributes
    ----------
    diameters:      Test diameters for holes and pegs in mm.
    plate_thickness: Z height of the hole plate in mm.
    peg_height:     Z height of cylindrical pegs in mm.
    peg_base_height: Z height of thin base under pegs in mm.
    column_spacing: X distance between hole/peg centres in mm.
    row_spacing:    Y distance between hole row and peg row in mm.
    plate_margin:   Margin around outermost holes on plate in mm.
    base_height:    Build plate adhesion layer height in mm.
    filament_type:  Label for filament type (e.g. ``"PLA"``).
    """

    diameters: tuple[float, ...] = DEFAULT_DIAMETERS
    plate_thickness: float = PLATE_THICKNESS
    peg_height: float = PEG_HEIGHT
    peg_base_height: float = PEG_BASE_HEIGHT
    column_spacing: float = COLUMN_SPACING
    row_spacing: float = ROW_SPACING
    plate_margin: float = PLATE_MARGIN
    base_height: float = BASE_HEIGHT
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def total_width(config: ToleranceTestConfig) -> float:
    """Return the total X extent of the model."""
    n = len(config.diameters)
    max_d = max(config.diameters)
    return (n - 1) * config.column_spacing + max_d + 2 * config.plate_margin


def total_depth(config: ToleranceTestConfig) -> float:
    """Return the total Y extent of the model."""
    max_d = max(config.diameters)
    return config.row_spacing + max_d + 2 * config.plate_margin


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _hole_positions_x(config: ToleranceTestConfig) -> list[float]:
    """Return X positions for hole/peg centres, centred around X=0."""
    n = len(config.diameters)
    total_span = (n - 1) * config.column_spacing
    start_x = -total_span / 2.0
    return [start_x + i * config.column_spacing for i in range(n)]


def _make_hole_plate(config: ToleranceTestConfig) -> cq.Workplane:
    """Create a rectangular plate with circular through-holes.

    The plate is centred at ``Y = +row_spacing / 2`` (the hole row) and
    sits on top of the base adhesion layer at ``Z = base_height``.
    """
    tw = total_width(config)
    max_d = max(config.diameters)
    plate_y = max_d + 2 * config.plate_margin

    plate = (
        cq.Workplane("XY")
        .box(
            tw,
            plate_y,
            config.plate_thickness,
            centered=(True, True, False),
        )
        .translate((0, config.row_spacing / 2.0, config.base_height))
    )

    # Cut circular through-holes
    positions = _hole_positions_x(config)
    for x_pos, diameter in zip(positions, config.diameters):
        hole = (
            cq.Workplane("XY")
            .circle(diameter / 2.0)
            .extrude(config.plate_thickness)
            .translate((x_pos, config.row_spacing / 2.0, config.base_height))
        )
        plate = plate.cut(hole)

    return plate


def _make_peg(
    config: ToleranceTestConfig,
    diameter: float,
    x: float,
    y: float,
) -> cq.Workplane:
    """Create a single cylindrical peg at the given position.

    The peg sits on top of the peg base at
    ``Z = base_height + peg_base_height``.
    """
    z_bottom = config.base_height + config.peg_base_height
    return (
        cq.Workplane("XY")
        .circle(diameter / 2.0)
        .extrude(config.peg_height)
        .translate((x, y, z_bottom))
    )


def _make_peg_row(config: ToleranceTestConfig) -> cq.Workplane:
    """Create all pegs on a shared thin base plate.

    The peg row is centred at ``Y = -row_spacing / 2`` and sits on top
    of the build plate adhesion layer.
    """
    tw = total_width(config)
    max_d = max(config.diameters)
    base_y = max_d + 2 * config.plate_margin
    peg_row_y = -config.row_spacing / 2.0

    # Thin base under pegs
    base = (
        cq.Workplane("XY")
        .box(
            tw,
            base_y,
            config.peg_base_height,
            centered=(True, True, False),
        )
        .translate((0, peg_row_y, config.base_height))
    )

    positions = _hole_positions_x(config)
    for x_pos, diameter in zip(positions, config.diameters):
        base = base.union(_make_peg(config, diameter, x_pos, peg_row_y))

    return base


def _make_tolerance_test(config: ToleranceTestConfig) -> cq.Workplane:
    """Build the complete tolerance test: base + hole plate + peg row."""
    # Shared adhesion base spanning both rows
    tw = total_width(config)
    td = total_depth(config)
    base = (
        cq.Workplane("XY")
        .box(tw, td, config.base_height, centered=(True, True, False))
    )

    hole_plate = _make_hole_plate(config)
    peg_row = _make_peg_row(config)

    return base.union(hole_plate).union(peg_row)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_tolerance_stl(
    config: ToleranceTestConfig,
    output_path: str,
) -> str:
    """One-shot: build the tolerance test model and export to STL.

    Parameters
    ----------
    config:      Tolerance test configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    shape = _make_tolerance_test(config)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
