"""CadQuery parametric chevron pattern model for PA calibration.

Generates nested V-shaped chevron outlines inside a rectangular frame,
matching the classic Ellis/Andrew Ellis PA calibration pattern.  Each
chevron is printed with a different pressure advance value — the user
inspects which chevron has the sharpest corners.

The STL is sliced by PrusaSlicer and then post-processed to insert PA
commands based on X position (see :mod:`pa_insert`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cadquery as cq  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Default constants (derived from Ellis PA tool)
# ---------------------------------------------------------------------------

DEFAULT_CORNER_ANGLE: float = 90.0
"""Full angle at the chevron tip in degrees."""

DEFAULT_ARM_LENGTH: float = 40.0
"""Length of each chevron arm in mm."""

DEFAULT_WALL_COUNT: int = 3
"""Number of concentric perimeters (passed to slicer, not CadQuery)."""

DEFAULT_NUM_LAYERS: int = 4
"""Number of printed layers."""

DEFAULT_PATTERN_SPACING: float = 1.6
"""Perpendicular gap between adjacent chevron arms in mm.

Defaults to ``DEFAULT_WALL_THICKNESS`` so the gap matches the line width.
"""

DEFAULT_WALL_THICKNESS: float = 1.6
"""Cross-section thickness of each chevron arm in mm."""

DEFAULT_FRAME_OFFSET: float = 3.0
"""Margin between outermost chevron arm and inner frame edge in mm."""

DEFAULT_LABEL_HEIGHT: float = 10.0
"""Height of the label strip placed above the frame in mm."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PAPatternConfig:
    """Configuration for the chevron pattern PA calibration model.

    Attributes
    ----------
    num_patterns:     Number of chevrons to generate.
    corner_angle:     Full angle at chevron tip in degrees.
    arm_length:       Length of each chevron arm in mm.
    wall_count:       Number of perimeters (forwarded to slicer).
    num_layers:       Number of printed layers.
    pattern_spacing:  Perpendicular gap between adjacent chevron arms in mm.
    wall_thickness:   Cross-section thickness of each arm in mm.
    frame_offset:     Margin between outermost chevron and frame inner edge.
    layer_height:     Slicer layer height in mm.
    filament_type:    Label (e.g. ``"PLA"``).
    """
    num_patterns: int
    corner_angle: float = DEFAULT_CORNER_ANGLE
    arm_length: float = DEFAULT_ARM_LENGTH
    wall_count: int = DEFAULT_WALL_COUNT
    num_layers: int = DEFAULT_NUM_LAYERS
    pattern_spacing: float = DEFAULT_PATTERN_SPACING
    wall_thickness: float = DEFAULT_WALL_THICKNESS
    frame_offset: float = DEFAULT_FRAME_OFFSET
    layer_height: float = 0.2
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def chevron_x_extent(arm_length: float, corner_angle: float) -> float:
    """Horizontal projection of one chevron arm.

    ``arm_length * cos(corner_angle / 2)``
    """
    half = math.radians(corner_angle / 2)
    return arm_length * math.cos(half)


def chevron_y_extent(arm_length: float, corner_angle: float) -> float:
    """Vertical extent of one chevron (tip to tip of both arms).

    ``2 * arm_length * sin(corner_angle / 2)``
    """
    half = math.radians(corner_angle / 2)
    return 2.0 * arm_length * math.sin(half)


def total_height(config: PAPatternConfig) -> float:
    """Total Z height of the printed pattern."""
    return config.num_layers * config.layer_height


def tip_spacing(config: PAPatternConfig) -> float:
    """Horizontal distance between adjacent chevron tips.

    ``pattern_spacing`` is the **edge-to-edge** gap between adjacent
    arms.  The perpendicular centre-to-centre distance is therefore
    ``pattern_spacing + wall_thickness``, and the horizontal distance
    between tips is ``(pattern_spacing + wall_thickness) / sin(α/2)``.
    """
    half = math.radians(config.corner_angle / 2)
    return (config.pattern_spacing + config.wall_thickness) / math.sin(half)


def pattern_x_tips(config: PAPatternConfig) -> List[float]:
    """Compute the X position of each chevron tip, centred at X = 0.

    Returns one float per chevron, left-to-right.
    """
    dx = tip_spacing(config)
    total_w = (config.num_patterns - 1) * dx
    start_x = -total_w / 2.0
    return [round(start_x + i * dx, 4) for i in range(config.num_patterns)]


# ---------------------------------------------------------------------------
# CadQuery model generation
# ---------------------------------------------------------------------------


def _chevron_outline(
    tip_x: float,
    arm_length: float,
    corner_angle: float,
    wall_thickness: float,
) -> List[Tuple[float, float]]:
    """Return the polygon vertices for a thick chevron (V-shape).

    The chevron points to the right.  Vertices are returned in order
    suitable for ``Workplane.polyline().close().extrude()``.
    """
    half = math.radians(corner_angle / 2)
    cos_a = math.cos(half)
    sin_a = math.sin(half)
    w = wall_thickness

    # Centre-line endpoints ---
    # Tip at (tip_x, 0).
    # Top arm left end: (tip_x - L*cos, L*sin).
    # Bottom arm: mirror.
    lx = tip_x - arm_length * cos_a
    ly = arm_length * sin_a

    # Perpendicular offsets ---
    # Top arm outward normal (away from V centre): (sin_a, cos_a).
    # Bottom arm outward normal: (sin_a, -cos_a).
    hw = w / 2.0  # half wall thickness

    # Outer tip: intersection of two outer edges.
    outer_tip_x = tip_x + hw / sin_a

    # Inner tip (notch): intersection of two inner edges.
    inner_tip_x = tip_x - hw / sin_a

    # Top arm left-end offsets.
    top_outer_lx = lx + hw * sin_a
    top_outer_ly = ly + hw * cos_a
    top_inner_lx = lx - hw * sin_a
    top_inner_ly = ly - hw * cos_a

    # Bottom arm left-end offsets (mirror Y).
    bot_inner_lx = lx - hw * sin_a
    bot_inner_ly = -(ly - hw * cos_a)
    bot_outer_lx = lx + hw * sin_a
    bot_outer_ly = -(ly + hw * cos_a)

    return [
        (outer_tip_x, 0.0),            # outer tip (rightmost)
        (top_outer_lx, top_outer_ly),   # outer top-left
        (top_inner_lx, top_inner_ly),   # inner top-left
        (inner_tip_x, 0.0),            # inner tip (notch)
        (bot_inner_lx, bot_inner_ly),   # inner bottom-left
        (bot_outer_lx, bot_outer_ly),   # outer bottom-left
    ]


def _make_chevron(
    tip_x: float,
    config: PAPatternConfig,
    height: float,
) -> cq.Workplane:
    """Create a single thick chevron prism with tip at *(tip_x, 0)*."""
    verts = _chevron_outline(
        tip_x, config.arm_length, config.corner_angle, config.wall_thickness,
    )
    return (
        cq.Workplane("XY")
        .polyline(verts)
        .close()
        .extrude(height)
    )


def _make_frame(
    config: PAPatternConfig,
    x_tips: List[float],
    height: float,
) -> cq.Workplane:
    """Create the rectangular frame enclosing all chevrons."""
    half = math.radians(config.corner_angle / 2)
    hw = config.wall_thickness / 2.0

    # Bounding box of all chevron outlines.
    rightmost_tip = max(x_tips)
    leftmost_tip = min(x_tips)
    arm_lx = leftmost_tip - config.arm_length * math.cos(half)

    # X bounds: from leftmost arm end (minus outer offset) to rightmost tip
    x_min = arm_lx - hw * math.sin(half) - config.frame_offset
    x_max = rightmost_tip + hw / math.sin(half) + config.frame_offset

    # Y bounds: from tallest arm extent (plus outer offset).
    y_max_arm = config.arm_length * math.sin(half) + hw * math.cos(half)
    y_min = -(y_max_arm + config.frame_offset)
    y_max = y_max_arm + config.frame_offset

    w = config.wall_thickness

    # Outer rectangle.
    outer = (
        cq.Workplane("XY")
        .moveTo(x_min, y_min)
        .lineTo(x_max, y_min)
        .lineTo(x_max, y_max)
        .lineTo(x_min, y_max)
        .close()
        .extrude(height)
    )

    # Inner rectangle (cut).
    inner = (
        cq.Workplane("XY")
        .moveTo(x_min + w, y_min + w)
        .lineTo(x_max - w, y_min + w)
        .lineTo(x_max - w, y_max - w)
        .lineTo(x_min + w, y_max - w)
        .close()
        .extrude(height)
    )

    return outer.cut(inner)


def _make_labels(
    config: PAPatternConfig,
    x_tips: List[float],
    pa_values: List[float],
    height: float,
) -> cq.Workplane:
    """Create the label strip with embossed PA values above the frame."""
    half = math.radians(config.corner_angle / 2)
    hw = config.wall_thickness / 2.0

    # Frame outer top edge Y.
    y_max_arm = config.arm_length * math.sin(half) + hw * math.cos(half)
    frame_top = y_max_arm + config.frame_offset

    # Label strip sits above the frame.
    label_strip_height = DEFAULT_LABEL_HEIGHT
    bar_cy = frame_top + label_strip_height / 2.0

    # Bar spans the full frame width.
    leftmost_tip = min(x_tips)
    rightmost_tip = max(x_tips)
    arm_lx = leftmost_tip - config.arm_length * math.cos(half)
    bar_x_min = arm_lx - hw * math.sin(half) - config.frame_offset
    bar_x_max = rightmost_tip + hw / math.sin(half) + config.frame_offset
    bar_width = bar_x_max - bar_x_min
    bar_cx = (bar_x_min + bar_x_max) / 2.0

    # Flat bar (same height as chevrons).
    bar = (
        cq.Workplane("XY")
        .box(bar_width, label_strip_height, height, centered=(True, True, False))
        .translate((bar_cx, bar_cy, 0))
    )

    # Emboss rotated labels on top of bar (90° CCW so they read bottom-to-top).
    # Position each label at the upper arm endpoint X (where the arm meets
    # the top of the frame), not at the tip X.
    arm_end_dx = config.arm_length * math.cos(half)
    label_depth = config.layer_height  # one layer raised
    font_size = min(3.0, label_strip_height * 0.35)
    result = bar
    for tx, pa in zip(x_tips, pa_values):
        label_x = tx - arm_end_dx
        label_text = f"{pa:.3f}"
        text_solid = (
            cq.Workplane("XY")
            .workplane(offset=height)
            .center(label_x, bar_cy)
            .transformed(rotate=(0, 0, 90))
            .text(label_text, font_size, label_depth, combine=False)
        )
        result = result.union(text_solid)

    return result


def generate_pa_pattern_stl(
    config: PAPatternConfig,
    output_path: str,
    pa_values: Optional[List[float]] = None,
) -> Tuple[str, List[float]]:
    """Generate the nested chevron pattern STL.

    Returns ``(output_path, x_tips)`` where *x_tips* lists each
    chevron's tip X coordinate (model-space, centred at 0).
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    height = total_height(config)
    x_tips = pattern_x_tips(config)

    # Build chevrons.
    result: cq.Workplane | None = None
    for tx in x_tips:
        chevron = _make_chevron(tx, config, height)
        if result is None:
            result = chevron
        else:
            result = result.union(chevron)

    # Add frame.
    frame = _make_frame(config, x_tips, height)
    result = result.union(frame)

    # Add labels if PA values are provided.
    if pa_values is not None and len(pa_values) == len(x_tips):
        labels = _make_labels(config, x_tips, pa_values, height)
        result = result.union(labels)

    cq.exporters.export(result, output_path)
    return output_path, x_tips
