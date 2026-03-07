"""Pressure advance G-code insertion for PA calibration prints.

Provides two insertion strategies:

* **Z-based** (tower method): uses ``gcode_lib.iter_layers()`` to identify
  Z-level boundaries and inserts PA commands at each height transition.
* **X-based** (pattern method): walks G-code line by line using
  ``gcode_lib.ModalState`` to track X position and inserts PA commands when
  the toolpath moves to a different diamond region.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import gcode_lib as gl

from gcode_lib import is_extrusion_move as _is_extrusion_move


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PALevel:
    """One pressure advance level's Z range and target PA value.

    Attributes
    ----------
    pa_value: Pressure advance value for this level.
    z_start:  Bottom of level (inclusive), in mm.
    z_end:    Top of level (exclusive), in mm.
    """
    pa_value: float
    z_start: float
    z_end: float


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def pa_command(pa_value: float, printer: str = "COREONE") -> str:
    """Return the G-code command to set pressure advance.

    The Prusa Mini uses Linear Advance (``M900 K``).  All other
    Prusa printers use Pressure Advance (``M572 S``).  This is
    consistent with :func:`filament_calibrator.ini_writer._pa_command`.

    Parameters
    ----------
    pa_value: The pressure advance value.
    printer:  Printer model name (default ``"COREONE"``).

    Returns
    -------
    str
        The G-code command string.
    """
    if printer.upper() == "MINI":
        return f"M900 K{pa_value:.4f} ; PA calibration level"
    return f"M572 S{pa_value:.4f} ; PA calibration level"


def compute_pa_levels(
    start_pa: float,
    pa_step: float,
    num_levels: int,
    level_height: float,
) -> List[PALevel]:
    """Calculate the Z ranges and PA values for each level.

    Level 0 (bottom) gets *start_pa*.  Each subsequent level increases
    by *pa_step*.

    Parameters
    ----------
    start_pa:     Lowest PA value (bottom level).
    pa_step:      PA value increase per level.
    num_levels:   Number of levels.
    level_height: Height of each level in mm.

    Returns
    -------
    List[PALevel]
        One entry per level, ordered bottom to top.
    """
    levels: List[PALevel] = []
    for i in range(num_levels):
        z_start = i * level_height
        z_end = z_start + level_height
        pa_value = round(start_pa + i * pa_step, 4)
        levels.append(PALevel(
            pa_value=pa_value,
            z_start=z_start,
            z_end=z_end,
        ))
    return levels


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _level_for_z(z: float, levels: List[PALevel]) -> PALevel | None:
    """Return the level that contains height *z*, or ``None``."""
    for level in levels:
        if level.z_start <= z < level.z_end:
            return level
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def insert_pa_commands(
    lines: List[gl.GCodeLine],
    levels: List[PALevel],
    *,
    printer: str = "COREONE",
) -> List[gl.GCodeLine]:
    """Insert pressure advance commands at level boundaries.

    Walks the G-code layer by layer using :func:`gcode_lib.iter_layers`.
    When a layer's Z height crosses into a new PA level, a PA command
    is inserted before that layer's first line.

    Returns a new list of :class:`gcode_lib.GCodeLine` (following the
    immutable-input convention from gcode-lib).

    Parameters
    ----------
    lines:    Parsed G-code lines.
    levels:   PA levels from :func:`compute_pa_levels`.
    printer:  Printer model name (determines M900 vs M572).
    """
    if not levels:
        return list(lines)

    result: List[gl.GCodeLine] = []
    prev_pa: float | None = None

    for z_height, layer_lines in gl.iter_layers(lines):
        level = _level_for_z(z_height, levels)
        if level is not None:
            target_pa = level.pa_value
        else:
            # Above the last level — keep previous PA
            target_pa = prev_pa

        if target_pa is not None and target_pa != prev_pa:
            cmd = pa_command(target_pa, printer=printer)
            result.append(gl.parse_line(cmd))
            prev_pa = target_pa

        result.extend(layer_lines)

    return result


# ---------------------------------------------------------------------------
# X-based insertion (pattern method)
# ---------------------------------------------------------------------------


@dataclass
class PAPatternRegion:
    """One diamond pattern's X region and PA value.

    Attributes
    ----------
    pa_value: Pressure advance value for this pattern.
    x_start:  Left boundary (inclusive), in mm.
    x_end:    Right boundary (exclusive), in mm.
    """
    pa_value: float
    x_start: float
    x_end: float


def compute_pa_pattern_regions(
    pa_values: List[float],
    x_centers: List[float],
) -> List[PAPatternRegion]:
    """Build X-axis regions for each diamond pattern.

    Region boundaries are placed at the midpoint between adjacent
    diamond centres.  The leftmost region extends to ``-inf`` and the
    rightmost extends to ``+inf``.

    Parameters
    ----------
    pa_values: PA value for each pattern (left to right).
    x_centers: X coordinate of each diamond's centre (left to right).

    Returns
    -------
    List[PAPatternRegion]
        One region per pattern, ordered left to right.
    """
    regions: List[PAPatternRegion] = []
    n = len(pa_values)
    for i in range(n):
        x_start = (
            float("-inf")
            if i == 0
            else (x_centers[i - 1] + x_centers[i]) / 2.0
        )
        x_end = (
            float("inf")
            if i == n - 1
            else (x_centers[i] + x_centers[i + 1]) / 2.0
        )
        regions.append(PAPatternRegion(
            pa_value=pa_values[i],
            x_start=x_start,
            x_end=x_end,
        ))
    return regions


def _region_for_x(
    x: float,
    regions: List[PAPatternRegion],
) -> PAPatternRegion | None:
    """Return the region that contains *x*, or ``None``."""
    for region in regions:
        if region.x_start <= x < region.x_end:
            return region
    return None


def insert_pa_pattern_commands(
    lines: List[gl.GCodeLine],
    regions: List[PAPatternRegion],
    *,
    printer: str = "COREONE",
) -> List[gl.GCodeLine]:
    """Insert PA commands based on the toolpath's X position.

    Walks G-code line by line using :class:`gcode_lib.ModalState` to
    track the current X coordinate.  When an extrusion move enters a
    different diamond's X region, a PA command is inserted before it.

    Returns a new list of :class:`gcode_lib.GCodeLine`.

    Parameters
    ----------
    lines:    Parsed G-code lines.
    regions:  Pattern regions from :func:`compute_pa_pattern_regions`.
    printer:  Printer model name (determines M900 vs M572).
    """
    if not regions:
        return list(lines)

    result: List[gl.GCodeLine] = []
    state = gl.ModalState()
    prev_pa: float | None = None

    for line in lines:
        gl.advance_state(state, line)

        if _is_extrusion_move(line):
            region = _region_for_x(state.x, regions)
            if region is not None and region.pa_value != prev_pa:
                cmd = pa_command(region.pa_value, printer=printer)
                result.append(gl.parse_line(cmd))
                prev_pa = region.pa_value

        result.append(line)

    return result
