"""Temperature G-code insertion for temperature tower prints.

Uses ``gcode_lib.iter_layers()`` to identify Z-level boundaries and inserts
``M104 S{temp}`` commands at the start of each temperature tier.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import gcode_lib as gl

from filament_calibrator._insert_helpers import (
    insert_commands_by_z,
    level_for_z,
)
from filament_calibrator.model import BASE_HEIGHT, TIER_HEIGHT


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TempTier:
    """One temperature tier's Z range and target temperature.

    Attributes
    ----------
    temp:    Target hotend temperature in °C.
    z_start: Bottom of tier (inclusive), in mm.
    z_end:   Top of tier (inclusive), in mm.
    """
    temp: int
    z_start: float
    z_end: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_temp_tiers(
    start_temp: int,
    temp_step: int,
    num_tiers: int,
    base_height: float = BASE_HEIGHT,
    tier_height: float = TIER_HEIGHT,
) -> List[TempTier]:
    """Calculate the Z ranges and temperatures for each tier.

    Tier 0 (bottom) gets *start_temp*.  Each subsequent tier is *temp_step*
    degrees cooler.  The base plate (Z 0 → *base_height*) is **not** a
    temperature tier — it prints at the first tier's temperature.

    Parameters
    ----------
    start_temp:  Highest temperature (bottom tier).
    temp_step:   Temperature decrease per tier.
    num_tiers:   Number of tiers.
    base_height: Height of the base plate in mm.
    tier_height: Height of each tier in mm.

    Returns
    -------
    List[TempTier]
        One entry per tier, ordered bottom to top (hottest to coolest).
    """
    tiers: List[TempTier] = []
    for i in range(num_tiers):
        z_start = base_height + i * tier_height
        z_end = z_start + tier_height
        temp = start_temp - i * temp_step
        tiers.append(TempTier(temp=temp, z_start=z_start, z_end=z_end))
    return tiers


# Re-export under the original name used by tests.
_tier_for_z = level_for_z


def insert_temperatures(
    lines: List[gl.GCodeLine],
    tiers: List[TempTier],
) -> List[gl.GCodeLine]:
    """Insert ``M104`` temperature commands at tier boundaries.

    Walks the G-code layer by layer using :func:`gcode_lib.iter_layers`.
    When a layer's Z height crosses into a new tier, an ``M104 S{temp}``
    command is inserted before that layer's first line.

    The base plate layers (below the first tier's ``z_start``) receive the
    first tier's temperature.

    Returns a new list of :class:`gcode_lib.GCodeLine` (following the
    immutable-input convention from gcode-lib).

    Parameters
    ----------
    lines: Parsed G-code lines.
    tiers: Temperature tiers from :func:`compute_temp_tiers`.
    """
    return insert_commands_by_z(
        lines, tiers,
        get_value=lambda t: t.temp,
        make_command=lambda temp: f"M104 S{temp} ; temp tower tier",
    )
