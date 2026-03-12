"""Feedrate G-code insertion for volumetric flow calibration prints.

Walks G-code line by line, tracking the current Z height via
``gcode_lib.ModalState``.  When Z crosses into a new flow level the
feedrate on extrusion moves is overridden to achieve the target
volumetric flow rate.

Low-level helpers (``flow_to_feedrate``, ``is_extrusion_move``) are
imported from ``gcode_lib`` (>= 1.1.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import gcode_lib as gl
from gcode_lib import flow_to_feedrate


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FlowLevel:
    """One flow-rate level's Z range and target feedrate.

    Attributes
    ----------
    flow_rate: Target volumetric flow rate in mm³/s.
    z_start:   Bottom of level (inclusive), in mm.
    z_end:     Top of level (inclusive), in mm.
    feedrate:  Computed feedrate in mm/min that achieves *flow_rate*.
    """
    flow_rate: float
    z_start: float
    z_end: float
    feedrate: float


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def compute_flow_levels(
    start_flow: float,
    flow_step: float,
    num_levels: int,
    level_height: float,
    layer_height: float,
    extrusion_width: float,
) -> List[FlowLevel]:
    """Calculate the Z ranges and feedrates for each flow level.

    Level 0 (bottom) gets *start_flow*.  Each subsequent level increases
    by *flow_step*.

    Parameters
    ----------
    start_flow:      Lowest volumetric flow rate (mm³/s, bottom level).
    flow_step:       Flow rate increase per level (mm³/s).
    num_levels:      Number of levels.
    level_height:    Height of each level in mm.
    layer_height:    Slicer layer height in mm.
    extrusion_width: Slicer extrusion width in mm.

    Returns
    -------
    List[FlowLevel]
        One entry per level, ordered bottom to top (slowest to fastest).
    """
    levels: List[FlowLevel] = []
    for i in range(num_levels):
        z_start = i * level_height
        z_end = z_start + level_height
        flow = start_flow + i * flow_step
        feedrate = flow_to_feedrate(flow, layer_height, extrusion_width)
        levels.append(FlowLevel(
            flow_rate=flow,
            z_start=z_start,
            z_end=z_end,
            feedrate=feedrate,
        ))
    return levels


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _level_for_z(z: float, levels: List[FlowLevel]) -> FlowLevel | None:
    """Return the level that contains height *z*, or ``None``."""
    for level in levels:
        if level.z_start <= z <= level.z_end:
            return level
    return None


# Import from gcode-lib under the private name used throughout this module.
_is_extrusion_move = gl.is_extrusion_move


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def insert_flow_rates(
    lines: List[gl.GCodeLine],
    levels: List[FlowLevel],
) -> List[gl.GCodeLine]:
    """Override feedrates in G-code to achieve target volumetric flow at each level.

    Walks the G-code line by line using :class:`gcode_lib.ModalState` to
    track the current Z height.  When a line falls within a flow level and
    is an extrusion move (G1 with E + X/Y), its ``F`` parameter is
    replaced with the level's target feedrate.

    Returns a new list of :class:`gcode_lib.GCodeLine` (following the
    immutable-input convention from gcode-lib).

    Parameters
    ----------
    lines:  Parsed G-code lines.
    levels: Flow levels from :func:`compute_flow_levels`.
    """
    if not levels:
        return list(lines)

    result: List[gl.GCodeLine] = []
    state = gl.ModalState()
    current_level: FlowLevel | None = None

    for line in lines:
        gl.advance_state(state, line)

        level = _level_for_z(state.z, levels)
        if level is not None:
            current_level = level

        if current_level is not None and _is_extrusion_move(line):
            new_raw = gl.replace_or_append(
                line.raw, "F", current_level.feedrate,
            )
            result.append(gl.parse_line(new_raw))
        else:
            result.append(line)

    return result
