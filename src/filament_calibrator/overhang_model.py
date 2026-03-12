"""Parametric overhang test model for overhang angle calibration.

Generates a back wall with angled ramp surfaces protruding from one side.
Each ramp tests a different overhang angle from vertical.  The user prints
the specimen, inspects the underside of each angled surface, and identifies
the maximum overhang angle the printer can handle cleanly without supports.

All dimensions are in millimetres.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_overhang_stl() to avoid
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

WALL_THICKNESS: float = 5.0
"""Y thickness of the back wall in mm."""

WALL_HEIGHT: float = 20.0
"""Z height of the back wall in mm."""

SURFACE_LENGTH: float = 25.0
"""How far each angled surface extends outward from the wall in mm."""

SURFACE_WIDTH: float = 15.0
"""X width of each overhang surface in mm."""

SURFACE_THICKNESS: float = 2.0
"""Thickness of each angled surface slab in mm."""

SURFACE_SPACING: float = 3.0
"""X gap between adjacent overhang surfaces in mm."""

BASE_HEIGHT: float = 1.0
"""Base plate height in mm (for bed adhesion)."""

BASE_MARGIN: float = 5.0
"""Margin around the model on the base plate in mm."""

DEFAULT_ANGLES: tuple[int, ...] = (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70)
"""Default overhang angles from vertical in degrees."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class OverhangTestConfig:
    """Parameters for the overhang calibration test model.

    Attributes
    ----------
    angles:            Overhang angles from vertical in degrees.
    wall_thickness:    Y thickness of the back wall in mm.
    wall_height:       Z height of the back wall in mm.
    surface_length:    How far each surface extends outward in mm.
    surface_width:     X width of each overhang surface in mm.
    surface_thickness: Thickness of each angled surface in mm.
    surface_spacing:   X gap between adjacent surfaces in mm.
    base_height:       Base plate height in mm.
    base_margin:       Margin around model on base in mm.
    filament_type:     Label for filament type (e.g. ``"PLA"``).
    """

    angles: tuple[int, ...] = DEFAULT_ANGLES
    wall_thickness: float = WALL_THICKNESS
    wall_height: float = WALL_HEIGHT
    surface_length: float = SURFACE_LENGTH
    surface_width: float = SURFACE_WIDTH
    surface_thickness: float = SURFACE_THICKNESS
    surface_spacing: float = SURFACE_SPACING
    base_height: float = BASE_HEIGHT
    base_margin: float = BASE_MARGIN
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def total_width(config: OverhangTestConfig) -> float:
    """Return the total X extent of all overhang surfaces."""
    n = len(config.angles)
    return n * (config.surface_width + config.surface_spacing) - config.surface_spacing


def total_depth(config: OverhangTestConfig) -> float:
    """Return the total Y extent (wall + maximum surface projection)."""
    return config.wall_thickness + config.surface_length


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_base(config: OverhangTestConfig) -> cq.Workplane:
    """Create the rectangular base plate centred at the XY origin."""
    tw = total_width(config)
    td = total_depth(config)
    base_x = tw + 2 * config.base_margin
    base_y = td + 2 * config.base_margin
    return (
        cq.Workplane("XY")
        .box(base_x, base_y, config.base_height, centered=(True, True, False))
    )


def _make_wall(config: OverhangTestConfig) -> cq.Workplane:
    """Create the tall rectangular back wall sitting on the base plate.

    The wall runs along the X axis at the back (negative Y side) of the
    model, centred in X.
    """
    tw = total_width(config)
    wall_x = tw + 2 * config.base_margin
    td = total_depth(config)
    # Wall is positioned at the back edge (negative Y half of total depth)
    wall_y_centre = -(td / 2.0) + config.wall_thickness / 2.0
    return (
        cq.Workplane("XY")
        .box(
            wall_x,
            config.wall_thickness,
            config.wall_height,
            centered=(True, True, False),
        )
        .translate((0, wall_y_centre, config.base_height))
    )


def _make_overhang_surface(
    config: OverhangTestConfig,
    angle_deg: int,
    x_position: float,
) -> cq.Workplane:
    """Create one angled overhang surface at the given X position.

    The surface is a rectangular slab rotated around the X axis so that it
    protrudes from the wall face at the specified overhang angle from
    vertical.  The rotation pivot is inside the wall so that the slab
    overlaps the wall and produces a proper boolean union.

    At ``angle_deg=0`` the surface is vertical (flush with wall); at
    ``angle_deg=90`` it would be fully horizontal.
    """
    td = total_depth(config)
    wall_y_front = -(td / 2.0) + config.wall_thickness
    pivot_z = config.base_height + config.wall_height

    # Cap surface length so the tip doesn't descend below the base plate.
    # After rotation, the tip Z = pivot_z - length * cos(angle).
    # We need tip Z >= base_height, so length <= wall_height / cos(angle).
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    if cos_a > 1e-9:
        max_length = config.wall_height / cos_a
    else:
        max_length = config.surface_length
    effective_length = min(config.surface_length, max_length)

    # Extend the slab downward (-Z) so that after rotation the extra
    # material ends up *inside* the wall volume, creating a proper
    # volumetric overlap for CadQuery's boolean union.
    #
    # Why -Z and not -Y?  The slab is rotated around the X axis by
    # -(90 - angle_deg).  Under that rotation a point at (0, 0, -d)
    # maps to y_rot = d·sin(θ) < 0 (into the wall) and
    # z_rot = -d·cos(θ) < 0 (below the pivot), which is inside the
    # wall for all angles 0 < angle < 90.  A -Y shift, by contrast,
    # would rotate *above* the pivot and miss the wall volume.
    overlap = config.wall_thickness / 2.0

    slab = (
        cq.Workplane("XY")
        .box(
            config.surface_width,
            effective_length,
            config.surface_thickness + overlap,
            centered=(True, False, False),
        )
        .translate((0, 0, -overlap))
    )

    # Rotation angle: overhang_angle is from vertical, so the rotation
    # from horizontal (the initial flat orientation) is (90 - angle_deg).
    # We rotate around the X axis.  Positive rotation tilts the far edge
    # upward; we want the far edge to tilt downward, so negate.
    rot_from_horizontal = 90.0 - angle_deg
    slab = slab.rotate((0, 0, 0), (1, 0, 0), -rot_from_horizontal)

    # Translate so the pivot (where the surface meets the wall) is at the
    # top-front of the wall.
    slab = slab.translate((x_position, wall_y_front, pivot_z))

    return slab


def _make_overhang_test(config: OverhangTestConfig) -> cq.Workplane:
    """Build the complete overhang test: base + wall + angled surfaces."""
    result = _make_base(config)
    result = result.union(_make_wall(config))

    tw = total_width(config)
    n = len(config.angles)
    # Centre the surfaces in X
    start_x = -tw / 2.0 + config.surface_width / 2.0
    step = config.surface_width + config.surface_spacing

    for i, angle in enumerate(config.angles):
        x_pos = start_x + i * step
        result = result.union(_make_overhang_surface(config, angle, x_pos))

    return result


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_overhang_stl(
    config: OverhangTestConfig,
    output_path: str,
) -> str:
    """One-shot: build the overhang test model and export to STL.

    Parameters
    ----------
    config:      Overhang test configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    shape = _make_overhang_test(config)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
