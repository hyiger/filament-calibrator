"""Shared helpers for Z-based G-code command insertion modules.

Provides two generic functions that are specialised by each insert module
(tempinsert, cooling_insert, retraction_insert, retraction_speed_insert,
pa_insert, flow_insert):

* :func:`level_for_z` — linear scan to find which level contains a given Z.
* :func:`insert_commands_by_z` — ``iter_layers``-based insertion loop that
  injects a G-code command whenever the Z height crosses into a new level.
"""
from __future__ import annotations

from typing import Any, Callable, List, Sequence, TypeVar

import gcode_lib as gl

_L = TypeVar("_L")


def level_for_z(z: float, levels: Sequence[_L]) -> _L | None:
    """Return the level whose ``z_start <= z <= z_end``, or ``None``.

    Works with any object that has ``z_start`` and ``z_end`` float
    attributes (e.g. ``TempTier``, ``CoolingLevel``, ``PALevel``).
    """
    for level in levels:
        if level.z_start <= z <= level.z_end:  # type: ignore[attr-defined]
            return level
    return None


def insert_commands_by_z(
    lines: List[gl.GCodeLine],
    levels: Sequence[_L],
    get_value: Callable[[_L], Any],
    make_command: Callable[[Any], str],
) -> List[gl.GCodeLine]:
    """Insert G-code commands at Z-level boundaries.

    Generic implementation of the ``iter_layers`` insertion pattern shared
    by temperature, cooling, retraction, retraction speed, and pressure
    advance insert modules.

    Parameters
    ----------
    lines:        Parsed G-code lines.
    levels:       Sorted level objects with ``z_start`` / ``z_end``.
    get_value:    Extract the comparable value from a level.
    make_command: Generate the G-code command string for a target value.
    """
    if not levels:
        return list(lines)

    result: List[gl.GCodeLine] = []
    prev_value: Any = None

    for z_height, layer_lines in gl.iter_layers(lines):
        level = level_for_z(z_height, levels)
        if level is not None:
            target = get_value(level)
        elif z_height < levels[0].z_start:  # type: ignore[attr-defined]
            # Base plate — use first level's value
            target = get_value(levels[0])
        else:
            # Above the last level — keep previous value
            target = prev_value

        if target is not None and target != prev_value:
            result.append(gl.parse_line(make_command(target)))
            prev_value = target

        result.extend(layer_lines)

    return result
