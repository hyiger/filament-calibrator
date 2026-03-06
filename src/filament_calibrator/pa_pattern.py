"""CadQuery parametric diamond pattern model for PA calibration.

Generates a row of hollow diamond (rhombus) prisms arranged side by side.
Each diamond is printed with a different pressure advance value so the user
can visually inspect which diamond has the sharpest corners.

The STL is sliced by PrusaSlicer and then post-processed to insert PA
commands based on X position (see :mod:`pa_insert`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import cadquery as cq  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Default constants (derived from Ellis PA tool)
# ---------------------------------------------------------------------------

DEFAULT_CORNER_ANGLE: float = 90.0
"""Diamond corner angle in degrees (acute angle at left/right vertices)."""

DEFAULT_SIDE_LENGTH: float = 30.0
"""Length of each diamond side in mm."""

DEFAULT_WALL_COUNT: int = 3
"""Number of concentric perimeters (passed to slicer, not CadQuery)."""

DEFAULT_NUM_LAYERS: int = 4
"""Number of printed layers."""

DEFAULT_PATTERN_SPACING: float = 2.0
"""Gap between adjacent diamonds in mm."""

DEFAULT_WALL_THICKNESS: float = 1.6
"""Shell thickness of hollow diamond in mm."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PAPatternConfig:
    """Configuration for the diamond pattern PA calibration model.

    Attributes
    ----------
    num_patterns:     Number of diamonds to generate.
    corner_angle:     Acute corner angle in degrees (left/right vertices).
    side_length:      Length of each diamond side in mm.
    wall_count:       Number of perimeters (forwarded to slicer).
    num_layers:       Number of printed layers.
    pattern_spacing:  Gap between adjacent diamonds in mm.
    wall_thickness:   Shell thickness of hollow diamond in mm.
    layer_height:     Slicer layer height in mm.
    filament_type:    Label (e.g. ``"PLA"``).
    """
    num_patterns: int
    corner_angle: float = DEFAULT_CORNER_ANGLE
    side_length: float = DEFAULT_SIDE_LENGTH
    wall_count: int = DEFAULT_WALL_COUNT
    num_layers: int = DEFAULT_NUM_LAYERS
    pattern_spacing: float = DEFAULT_PATTERN_SPACING
    wall_thickness: float = DEFAULT_WALL_THICKNESS
    layer_height: float = 0.2
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def diamond_width(side_length: float, corner_angle: float) -> float:
    """X extent of one diamond.

    ``2 * side_length * cos(corner_angle / 2)``
    """
    half = math.radians(corner_angle / 2)
    return 2.0 * side_length * math.cos(half)


def diamond_height(side_length: float, corner_angle: float) -> float:
    """Y extent of one diamond.

    ``2 * side_length * sin(corner_angle / 2)``
    """
    half = math.radians(corner_angle / 2)
    return 2.0 * side_length * math.sin(half)


def total_height(config: PAPatternConfig) -> float:
    """Total Z height of the printed pattern."""
    return config.num_layers * config.layer_height


def pattern_x_centers(config: PAPatternConfig) -> List[float]:
    """Compute the X centre of each diamond, centred at X = 0.

    Returns one float per diamond, left-to-right.
    """
    dw = diamond_width(config.side_length, config.corner_angle)
    total_w = (
        config.num_patterns * dw
        + (config.num_patterns - 1) * config.pattern_spacing
    )
    start_x = -total_w / 2.0 + dw / 2.0
    stride = dw + config.pattern_spacing
    return [round(start_x + i * stride, 4) for i in range(config.num_patterns)]


# ---------------------------------------------------------------------------
# CadQuery model generation
# ---------------------------------------------------------------------------


def _diamond_vertices(
    center_x: float,
    center_y: float,
    side_length: float,
    corner_angle: float,
) -> List[Tuple[float, float]]:
    """Return the four vertices of a diamond (right, top, left, bottom)."""
    half = math.radians(corner_angle / 2)
    dx = side_length * math.cos(half)
    dy = side_length * math.sin(half)
    return [
        (center_x + dx, center_y),      # right
        (center_x, center_y + dy),       # top
        (center_x - dx, center_y),       # left
        (center_x, center_y - dy),       # bottom
    ]


def _make_diamond(
    center_x: float,
    center_y: float,
    config: PAPatternConfig,
    height: float,
) -> cq.Workplane:
    """Create a single hollow diamond prism centred at *(center_x, 0)*."""
    outer_verts = _diamond_vertices(
        center_x, center_y, config.side_length, config.corner_angle,
    )

    # Build outer shell.
    outer = (
        cq.Workplane("XY")
        .polyline(outer_verts)
        .close()
        .extrude(height)
    )

    # Compute inner diamond by scaling inward using rhombus apothem.
    half = math.radians(config.corner_angle / 2)
    dx = config.side_length * math.cos(half)
    dy = config.side_length * math.sin(half)
    apothem = dx * dy / config.side_length  # perpendicular distance to edge

    if apothem <= config.wall_thickness:
        # Wall thickness fills entire diamond — return solid.
        return outer

    scale = (apothem - config.wall_thickness) / apothem
    inner_verts = [
        (center_x + dx * scale, center_y),
        (center_x, center_y + dy * scale),
        (center_x - dx * scale, center_y),
        (center_x, center_y - dy * scale),
    ]
    inner = (
        cq.Workplane("XY")
        .polyline(inner_verts)
        .close()
        .extrude(height)
    )
    return outer.cut(inner)


def generate_pa_pattern_stl(
    config: PAPatternConfig,
    output_path: str,
) -> Tuple[str, List[float]]:
    """Generate the side-by-side diamond pattern STL.

    Returns ``(output_path, x_centers)`` where *x_centers* lists each
    diamond's X centre coordinate (model-space, centred at 0).
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    height = total_height(config)
    x_centers = pattern_x_centers(config)

    result: cq.Workplane | None = None
    for cx in x_centers:
        diamond = _make_diamond(cx, 0.0, config, height)
        if result is None:
            result = diamond
        else:
            result = result.union(diamond)

    cq.exporters.export(result, output_path)
    return output_path, x_centers
