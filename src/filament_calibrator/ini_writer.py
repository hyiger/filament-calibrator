"""Merge calibration results into PrusaSlicer .ini config files.

Provides pure functions for line-by-line INI editing that preserves
comments, ordering, and formatting.  Low-level helpers
(``replace_ini_value``, ``pa_command``, ``inject_pa_into_start_gcode``)
are imported from ``gcode_lib`` (>= 1.1.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import gcode_lib as gl

# Re-import gcode-lib helpers under the private names used internally.
_replace_ini_value = gl.replace_ini_value
_pa_command = gl.pa_command
_inject_pa_into_start_gcode = gl.inject_pa_into_start_gcode


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class CalibrationResults:
    """Container for calibration values to merge into a slicer config.

    Fields that are ``None`` will not be written.
    """

    temperature: Optional[int] = None
    """Nozzle temperature in °C."""

    max_volumetric_speed: Optional[float] = None
    """Maximum volumetric flow rate in mm³/s."""

    pa_value: Optional[float] = None
    """Pressure advance / linear advance value."""

    extrusion_multiplier: Optional[float] = None
    """Extrusion multiplier (ratio).  ``1.0`` = nominal width."""

    printer: str = "COREONE"
    """Printer model name.  Determines the PA G-code command:
    ``"MINI"`` uses ``M900 K<value>`` (Linear Advance),
    all others use ``M572 S<value>`` (Pressure Advance)."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_results_into_ini(
    ini_text: str,
    results: CalibrationResults,
) -> str:
    """Merge *results* into *ini_text* and return the updated text.

    Only fields that are not ``None`` are written.  Existing values for
    those keys are replaced in-place; missing keys are appended.
    """
    lines = ini_text.splitlines()

    # --- Temperature ---
    if results.temperature is not None:
        temp_str = str(results.temperature)
        lines, found = _replace_ini_value(lines, "temperature", temp_str)
        if not found:
            lines.append(f"temperature = {temp_str}")
        lines, found = _replace_ini_value(
            lines, "first_layer_temperature", temp_str,
        )
        if not found:
            lines.append(f"first_layer_temperature = {temp_str}")

    # --- Max volumetric speed ---
    if results.max_volumetric_speed is not None:
        speed_str = f"{results.max_volumetric_speed:.1f}"
        lines, found = _replace_ini_value(
            lines, "filament_max_volumetric_speed", speed_str,
        )
        if not found:
            lines.append(f"filament_max_volumetric_speed = {speed_str}")

    # --- Pressure advance (injected into start_filament_gcode) ---
    if results.pa_value is not None:
        lines = _inject_pa_into_start_gcode(
            lines, results.pa_value, results.printer,
        )

    # --- Extrusion multiplier ---
    if results.extrusion_multiplier is not None:
        em_str = f"{results.extrusion_multiplier:.2f}"
        lines, found = _replace_ini_value(
            lines, "extrusion_multiplier", em_str,
        )
        if not found:
            lines.append(f"extrusion_multiplier = {em_str}")

    return "\n".join(lines) + "\n" if lines else ""


def build_change_summary(results: CalibrationResults) -> str:
    """Return a Markdown summary of the changes *results* will apply."""
    parts: List[str] = []

    if results.temperature is not None:
        parts.append(
            f"- **Nozzle temperature:** {results.temperature} °C "
            f"(`temperature`, `first_layer_temperature`)"
        )

    if results.max_volumetric_speed is not None:
        parts.append(
            f"- **Max volumetric speed:** "
            f"{results.max_volumetric_speed:.1f} mm³/s "
            f"(`filament_max_volumetric_speed`)"
        )

    if results.pa_value is not None:
        cmd = _pa_command(results.pa_value, results.printer)
        parts.append(
            f"- **Pressure advance:** `{cmd}` "
            f"(`start_filament_gcode`)"
        )

    if results.extrusion_multiplier is not None:
        parts.append(
            f"- **Extrusion multiplier:** "
            f"{results.extrusion_multiplier:.2f} "
            f"(`extrusion_multiplier`)"
        )

    if not parts:
        return "_No changes selected._"

    return "\n".join(parts)
