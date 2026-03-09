"""Parametric serpentine specimen model for volumetric flow testing.

Generates an E-shaped (serpentine/meandering) solid that, when sliced in
spiral vase mode, produces a long continuous perimeter path ideal for
sustained extrusion rate testing.  All dimensions are in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_flow_specimen_stl() to avoid
# loading the heavy OCCT/casadi native libraries at module-import time.
cq: Any = None  # populated by _ensure_cq()


def _ensure_cq() -> None:
    """Import cadquery on first use and cache in module globals."""
    global cq  # noqa: PLW0603
    if cq is None:
        import cadquery as _cq

        cq = _cq

# ---------------------------------------------------------------------------
# Geometry constants (defaults for the serpentine specimen)
# ---------------------------------------------------------------------------

SPECIMEN_WIDTH = 170.0   # overall X dimension (mm)
ARM_THICKNESS = 20.0     # thickness of each horizontal arm (Y, mm)
GAP_WIDTH = 20.0         # gap between arms (Y, mm)
NUM_ARMS = 3             # number of horizontal arms
LEVEL_HEIGHT = 1.0       # default height per flow level (mm)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class FlowSpecimenConfig:
    """Parameters for the flow-rate test specimen.

    Attributes
    ----------
    num_levels:    Number of flow-rate levels (one per ``level_height`` mm).
    level_height:  Height per level in mm.
    width:         Overall X dimension of the specimen.
    arm_thickness: Y thickness of each horizontal arm.
    gap_width:     Y gap between consecutive arms.
    num_arms:      Number of horizontal arms.
    filament_type: Label for filament type (e.g. ``"PLA"``).
    """
    num_levels: int
    level_height: float = LEVEL_HEIGHT
    width: float = SPECIMEN_WIDTH
    arm_thickness: float = ARM_THICKNESS
    gap_width: float = GAP_WIDTH
    num_arms: int = NUM_ARMS
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def specimen_depth(config: FlowSpecimenConfig) -> float:
    """Return the overall Y dimension of the specimen."""
    return config.num_arms * config.arm_thickness + (config.num_arms - 1) * config.gap_width


def total_height(config: FlowSpecimenConfig) -> float:
    """Return the total Z height of the specimen."""
    return config.num_levels * config.level_height


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_serpentine(config: FlowSpecimenConfig, height: float) -> cq.Workplane:
    """Build the serpentine E-shape solid.

    Construction:
    1. Create a full bounding rectangle (width × depth), extrude to *height*.
    2. Cut horizontal slots from the right side to create gaps between arms.
    3. Fillet all vertical edges to round the arm ends and inner corners.
    """
    depth = specimen_depth(config)

    # Full bounding block, centred at XY origin
    shape = (
        cq.Workplane("XY")
        .rect(config.width, depth)
        .extrude(height)
    )

    # Cut (num_arms - 1) slots from the right side.
    # The spine is on the left; each slot starts at the spine's right edge
    # and extends to the right boundary.
    slot_length = config.width - config.arm_thickness
    for i in range(config.num_arms - 1):
        # Y centre of the i-th gap (relative to shape centre)
        slot_y = (
            -depth / 2
            + config.arm_thickness * (i + 1)
            + config.gap_width * i
            + config.gap_width / 2
        )
        # X centre: shifted right so the slot starts at the spine boundary
        slot_x = config.arm_thickness / 2

        slot = (
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(slot_x, slot_y, 0))
            .rect(slot_length, config.gap_width)
            .extrude(height)
        )
        shape = shape.cut(slot)

    # Round vertical edges in multiple passes so that each edge group gets
    # the largest radius the geometry allows:
    #   • inner gap corners  → gap_width / 2
    #   • right-side arm ends → arm_thickness / 2
    #   • left-side spine corners → arm_thickness  (sweeping U-turn)
    inner_r = config.gap_width / 2 - 0.01
    outer_r = config.arm_thickness / 2 - 0.01
    spine_r = config.arm_thickness - 0.5
    spine_right_x = -config.width / 2 + config.arm_thickness

    # Pass 1 — inner gap edges (at x ≈ spine_right_x, smallest radius).
    shape = (
        shape.edges("|Z")
        .edges(cq.selectors.BoxSelector(
            (spine_right_x - 0.5, -depth / 2 - 0.5, -0.5),
            (spine_right_x + 0.5, depth / 2 + 0.5, height + 0.5),
        ))
        .fillet(inner_r)
    )

    # Pass 2 — right-side outer edges (arm ends).
    shape = (
        shape.edges("|Z")
        .edges(cq.selectors.BoxSelector(
            (config.width / 2 - 0.5, -depth / 2 - 0.5, -0.5),
            (config.width / 2 + 0.5, depth / 2 + 0.5, height + 0.5),
        ))
        .fillet(outer_r)
    )

    # Pass 3 — left-side spine corners (large sweeping radius).
    shape = (
        shape.edges("|Z")
        .edges(cq.selectors.BoxSelector(
            (-config.width / 2 - 0.5, -depth / 2 - 0.5, -0.5),
            (-config.width / 2 + 0.5, depth / 2 + 0.5, height + 0.5),
        ))
        .fillet(spine_r)
    )

    return shape


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_flow_specimen_stl(
    config: FlowSpecimenConfig,
    output_path: str,
) -> str:
    """One-shot: build the serpentine specimen and export to STL.

    Parameters
    ----------
    config:      Specimen configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    height = total_height(config)
    shape = _make_serpentine(config, height)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
