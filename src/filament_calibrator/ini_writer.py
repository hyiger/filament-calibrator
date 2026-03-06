"""Merge calibration results into PrusaSlicer .ini config files.

Provides pure functions for line-by-line INI editing that preserves
comments, ordering, and formatting.  No ``configparser`` is used for
writing — values are replaced via regex on individual lines so the
output is a minimal diff from the input.
"""
from __future__ import annotations

import dataclasses
import re
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclasses.dataclass
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
# Low-level helpers
# ---------------------------------------------------------------------------

def _replace_ini_value(
    lines: List[str],
    key: str,
    new_value: str,
) -> Tuple[List[str], bool]:
    """Replace the first occurrence of *key* ``= …`` with *new_value*.

    Returns ``(updated_lines, found)``.  Only the **first** matching line
    is replaced; subsequent duplicates are left untouched.  The
    whitespace around ``=`` is preserved from the original line.
    """
    pattern = re.compile(
        rf"^(\s*{re.escape(key)}\s*=\s*)(.*)$",
    )
    found = False
    result: List[str] = []
    for line in lines:
        if not found:
            m = pattern.match(line)
            if m:
                result.append(f"{m.group(1)}{new_value}")
                found = True
                continue
        result.append(line)
    return result, found


def _pa_command(pa_value: float, printer: str) -> str:
    """Return the G-code command string for setting pressure advance.

    The Prusa Mini uses Linear Advance (``M900 K``).  All other
    Prusa printers use Pressure Advance (``M572 S``).
    """
    if printer.upper() == "MINI":
        return f"M900 K{pa_value:.4f}"
    return f"M572 S{pa_value:.4f}"


_PA_LINE_RE = re.compile(
    r"(M572\s+S[\d.]+|M900\s+K[\d.]+)",
    re.IGNORECASE,
)


def _inject_pa_into_start_gcode(
    lines: List[str],
    pa_value: float,
    printer: str,
) -> List[str]:
    r"""Insert or replace a PA command inside ``start_filament_gcode``.

    PrusaSlicer stores multi-line G-code values on a single INI line
    using literal ``\n`` escape sequences, e.g.::

        start_filament_gcode = "M572 S0.04\nG92 E0"

    This function finds the ``start_filament_gcode`` key, then either
    replaces an existing PA command within the value or prepends one.
    If the key is absent the line is appended at the end.
    """
    pa_cmd = _pa_command(pa_value, printer)
    key_re = re.compile(r"^(\s*start_filament_gcode\s*=\s*)(.*)$")

    result: List[str] = []
    found = False

    for line in lines:
        if not found:
            m = key_re.match(line)
            if m:
                found = True
                prefix = m.group(1)
                raw_value = m.group(2)
                # Unquote if surrounded by quotes.
                stripped = raw_value.strip()
                if (
                    len(stripped) >= 2
                    and stripped[0] == '"'
                    and stripped[-1] == '"'
                ):
                    inner = stripped[1:-1]
                    quote = True
                else:
                    inner = stripped
                    quote = False

                if _PA_LINE_RE.search(inner):
                    # Replace existing PA command.
                    inner = _PA_LINE_RE.sub(pa_cmd, inner, count=1)
                elif inner:
                    # Prepend PA command before existing content.
                    inner = pa_cmd + "\\n" + inner
                else:
                    inner = pa_cmd

                if quote:
                    result.append(f'{prefix}"{inner}"')
                else:
                    result.append(f"{prefix}{inner}")
                continue
        result.append(line)

    if not found:
        result.append(f"start_filament_gcode = {pa_cmd}")

    return result


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
