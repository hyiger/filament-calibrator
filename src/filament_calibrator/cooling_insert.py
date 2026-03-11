"""Fan-speed G-code insertion for cooling calibration prints.

Uses ``gcode_lib.iter_layers()`` to identify Z-level boundaries and inserts
``M106 S{value}`` fan-speed commands at the start of each level.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import gcode_lib as gl


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CoolingLevel:
    """One cooling level's Z range and target fan percentage.

    Attributes
    ----------
    fan_percent: Fan speed percentage (0-100).
    z_start:     Bottom of level (inclusive), in mm.
    z_end:       Top of level (exclusive), in mm.
    """
    fan_percent: int
    z_start: float
    z_end: float


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def fan_command(percent: int) -> str:
    """Return the G-code command to set fan speed.

    Converts the percentage (0-100) to the 0-255 PWM range used by
    ``M106 S``.
    """
    return f"M106 S{round(percent * 255 / 100)} ; cooling calibration level"


def compute_cooling_levels(
    start_percent: int,
    percent_step: int,
    num_levels: int,
    level_height: float,
    base_height: float = 0.0,
) -> List[CoolingLevel]:
    """Calculate the Z ranges and fan percentages for each level.

    Level 0 (bottom) gets *start_percent*.  Each subsequent level increases
    by *percent_step*.  The base plate (Z 0 -> *base_height*) is **not** a
    cooling level -- it prints at the first level's fan percentage.

    Parameters
    ----------
    start_percent: Fan speed percentage for the bottom level (0-100).
    percent_step:  Fan speed increase per level in percentage points.
    num_levels:    Number of levels.
    level_height:  Height of each level in mm.
    base_height:   Height of the base plate in mm.

    Returns
    -------
    List[CoolingLevel]
        One entry per level, ordered bottom to top (lowest to highest fan).
    """
    levels: List[CoolingLevel] = []
    for i in range(num_levels):
        z_start = base_height + i * level_height
        z_end = z_start + level_height
        value = int(round(start_percent + i * percent_step))
        levels.append(
            CoolingLevel(
                fan_percent=value,
                z_start=round(z_start, 4),
                z_end=round(z_end, 4),
            ),
        )
    return levels


def _level_for_z(
    z: float,
    levels: List[CoolingLevel],
) -> CoolingLevel | None:
    """Return the level that contains height *z*, or ``None``."""
    for level in levels:
        if level.z_start <= z < level.z_end:
            return level
    return None


def insert_cooling_commands(
    lines: List[gl.GCodeLine],
    levels: List[CoolingLevel],
) -> List[gl.GCodeLine]:
    """Insert ``M106`` fan-speed commands at level boundaries.

    Walks the G-code layer by layer using :func:`gcode_lib.iter_layers`.
    When a layer's Z height crosses into a new level, an ``M106 S{value}``
    command is inserted before that layer's lines.

    The base plate layers (below the first level's ``z_start``) receive the
    first level's fan percentage.

    Returns a new list of :class:`gcode_lib.GCodeLine` (following the
    immutable-input convention from gcode-lib).

    Parameters
    ----------
    lines:  Parsed G-code lines.
    levels: Cooling levels from :func:`compute_cooling_levels`.
    """
    if not levels:
        return list(lines)

    result: List[gl.GCodeLine] = []
    prev_percent: int | None = None

    for z_height, layer_lines in gl.iter_layers(lines):
        level = _level_for_z(z_height, levels)
        if level is not None:
            target_percent = level.fan_percent
        elif z_height < levels[0].z_start:
            # Base plate — use first level's fan percentage
            target_percent = levels[0].fan_percent
        else:
            # Above the last level — keep previous fan percentage
            target_percent = prev_percent

        if target_percent is not None and target_percent != prev_percent:
            cmd = fan_command(target_percent)
            result.append(gl.parse_line(cmd))
            prev_percent = target_percent

        result.extend(layer_lines)

    return result
