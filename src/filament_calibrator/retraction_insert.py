"""Retraction length G-code insertion for retraction calibration prints.

Uses ``gcode_lib.iter_layers()`` to identify Z-level boundaries and inserts
``M207 S{length}`` firmware-retraction commands at the start of each level.
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
class RetractionLevel:
    """One retraction level's Z range and target retraction length.

    Attributes
    ----------
    retraction_length: Firmware retraction length in mm.
    z_start:           Bottom of level (inclusive), in mm.
    z_end:             Top of level (inclusive), in mm.
    """
    retraction_length: float
    z_start: float
    z_end: float


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def retraction_command(length: float) -> str:
    """Return the G-code command to set firmware retraction length.

    Uses ``M207 S`` (Set Firmware Retraction) which is supported by both
    Marlin and Klipper (via its G-code compatibility layer).
    """
    return f"M207 S{length:.2f} ; retraction calibration level"


def compute_retraction_levels(
    start_length: float,
    length_step: float,
    num_levels: int,
    level_height: float,
    base_height: float = 0.0,
) -> List[RetractionLevel]:
    """Calculate the Z ranges and retraction lengths for each level.

    Level 0 (bottom) gets *start_length*.  Each subsequent level increases
    by *length_step*.  The base plate (Z 0 → *base_height*) is **not** a
    retraction level — it prints at the first level's retraction length.

    Parameters
    ----------
    start_length: Retraction length for the bottom level in mm.
    length_step:  Retraction length increase per level in mm.
    num_levels:   Number of levels.
    level_height: Height of each level in mm.
    base_height:  Height of the base plate in mm.

    Returns
    -------
    List[RetractionLevel]
        One entry per level, ordered bottom to top (shortest to longest).
    """
    levels: List[RetractionLevel] = []
    for i in range(num_levels):
        z_start = base_height + i * level_height
        z_end = z_start + level_height
        length = round(start_length + i * length_step, 2)
        levels.append(
            RetractionLevel(
                retraction_length=length,
                z_start=round(z_start, 4),
                z_end=round(z_end, 4),
            ),
        )
    return levels


def insert_retraction_commands(
    lines: List[gl.GCodeLine],
    levels: List[RetractionLevel],
) -> List[gl.GCodeLine]:
    """Insert ``M207`` retraction-length commands at level boundaries.

    Walks the G-code layer by layer using :func:`gcode_lib.iter_layers`.
    When a layer's Z height crosses into a new level, an ``M207 S{length}``
    command is inserted before that layer's lines.

    The base plate layers (below the first level's ``z_start``) receive the
    first level's retraction length.

    Returns a new list of :class:`gcode_lib.GCodeLine` (following the
    immutable-input convention from gcode-lib).

    Parameters
    ----------
    lines:  Parsed G-code lines.
    levels: Retraction levels from :func:`compute_retraction_levels`.
    """
    return insert_commands_by_z(
        lines, levels,
        get_value=lambda lv: lv.retraction_length,
        make_command=retraction_command,
    )
