"""Retraction speed G-code insertion for retraction speed calibration prints.

Uses ``gcode_lib.iter_layers()`` to identify Z-level boundaries and inserts
``M207 S{length} F{speed}`` firmware-retraction commands at the start of each
level, varying the retraction speed while keeping the retraction length fixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import gcode_lib as gl

from filament_calibrator._insert_helpers import (
    insert_commands_by_z,
    level_for_z as _level_for_z,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RetractionSpeedLevel:
    """One retraction speed level's Z range and target speed.

    Attributes
    ----------
    speed_mm_s: Firmware retraction speed in mm/s.
    z_start:    Bottom of level (inclusive), in mm.
    z_end:      Top of level (inclusive), in mm.
    """
    speed_mm_s: float
    z_start: float
    z_end: float


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def retraction_speed_command(length: float, speed_mm_s: float) -> str:
    """Return the G-code command to set firmware retraction length and speed.

    Uses ``M207 S F`` (Set Firmware Retraction) which is supported by both
    Marlin and Klipper (via its G-code compatibility layer).  The ``F``
    parameter sets the retraction feedrate in mm/min.
    """
    return (
        f"M207 S{length:.2f} F{speed_mm_s * 60:.0f} "
        f"; retraction speed calibration level"
    )


def compute_retraction_speed_levels(
    start_speed: float,
    speed_step: float,
    num_levels: int,
    level_height: float,
    base_height: float = 0.0,
) -> List[RetractionSpeedLevel]:
    """Calculate the Z ranges and retraction speeds for each level.

    Level 0 (bottom) gets *start_speed*.  Each subsequent level increases
    by *speed_step*.  The base plate (Z 0 → *base_height*) is **not** a
    retraction speed level — it prints at the first level's speed.

    Parameters
    ----------
    start_speed:  Retraction speed for the bottom level in mm/s.
    speed_step:   Retraction speed increase per level in mm/s.
    num_levels:   Number of levels.
    level_height: Height of each level in mm.
    base_height:  Height of the base plate in mm.

    Returns
    -------
    List[RetractionSpeedLevel]
        One entry per level, ordered bottom to top (slowest to fastest).
    """
    levels: List[RetractionSpeedLevel] = []
    for i in range(num_levels):
        z_start = base_height + i * level_height
        z_end = z_start + level_height
        speed = round(start_speed + i * speed_step, 1)
        levels.append(
            RetractionSpeedLevel(
                speed_mm_s=speed,
                z_start=round(z_start, 4),
                z_end=round(z_end, 4),
            ),
        )
    return levels


def insert_retraction_speed_commands(
    lines: List[gl.GCodeLine],
    levels: List[RetractionSpeedLevel],
    retraction_length: float,
) -> List[gl.GCodeLine]:
    """Insert ``M207`` retraction-speed commands at level boundaries.

    Walks the G-code layer by layer using :func:`gcode_lib.iter_layers`.
    When a layer's Z height crosses into a new level, an ``M207 S{length}
    F{speed}`` command is inserted before that layer's lines.

    The base plate layers (below the first level's ``z_start``) receive the
    first level's retraction speed.

    Returns a new list of :class:`gcode_lib.GCodeLine` (following the
    immutable-input convention from gcode-lib).

    Parameters
    ----------
    lines:              Parsed G-code lines.
    levels:             Retraction speed levels from
                        :func:`compute_retraction_speed_levels`.
    retraction_length:  Fixed retraction length in mm.
    """
    return insert_commands_by_z(
        lines, levels,
        get_value=lambda lv: lv.speed_mm_s,
        make_command=lambda speed: retraction_speed_command(
            retraction_length, speed,
        ),
    )
