"""PrusaSlicer .ini config file parser for GUI auto-population.

Extracts relevant slicer settings from a PrusaSlicer exported config
file (.ini format) and returns them as a typed dictionary suitable for
populating GUI fields.
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def _first_value(raw: str) -> str:
    """Return the first semicolon-delimited value from *raw*.

    PrusaSlicer uses semicolons to separate per-extruder values
    (e.g. ``"0.4;0.4"`` for dual-extruder nozzle_diameter).
    """
    return raw.split(";")[0].strip()


def _parse_float(raw: str) -> Optional[float]:
    """Parse a float from the first semicolon-delimited value.

    Returns ``None`` on failure.
    """
    try:
        return float(_first_value(raw))
    except (ValueError, IndexError):
        return None


def _parse_int(raw: str) -> Optional[int]:
    """Parse an int (truncating any decimal part) from the first value.

    Returns ``None`` on failure.
    """
    f = _parse_float(raw)
    return int(f) if f is not None else None


def _parse_extrusion_width(raw: str) -> Optional[float]:
    """Parse extrusion width, which may be ``"0"`` (auto), a percentage, or mm.

    Returns a positive float in mm, or ``None`` when the value is auto,
    a percentage string, or otherwise unparseable.
    """
    val = _first_value(raw)
    if val == "0" or val == "":
        return None  # auto
    if val.endswith("%"):
        return None  # percentage-based; not convertible without nozzle size
    try:
        result = float(val)
        return result if result > 0 else None
    except ValueError:
        return None


def _parse_bed_shape(raw: str) -> Optional[str]:
    """Parse PrusaSlicer ``bed_shape`` and compute the bed centre.

    The expected format is ``"0x0,250x0,250x210,0x210"`` — four corners
    of a rectangle with ``x`` as coordinate separator within each
    corner.  Returns the centre as ``"X,Y"`` (integer coordinates), or
    ``None`` when the value is malformed.
    """
    try:
        corners = raw.split(",")
        xs = []
        ys = []
        for corner in corners:
            parts = corner.strip().split("x")
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
        cx = int((min(xs) + max(xs)) / 2)
        cy = int((min(ys) + max(ys)) / 2)
        return f"{cx},{cy}"
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_prusaslicer_ini(path: str) -> Dict[str, Any]:
    """Parse a PrusaSlicer ``.ini`` file and extract GUI-relevant settings.

    The returned dict may contain any subset of these keys:

    - ``nozzle_diameter`` (float): Nozzle diameter in mm.
    - ``nozzle_temp`` (int): Nozzle temperature in °C.
    - ``bed_temp`` (int): Bed temperature in °C.
    - ``fan_speed`` (int): Fan speed 0–100%.
    - ``layer_height`` (float): Layer height in mm.
    - ``extrusion_width`` (float): Extrusion width in mm (only if explicit).
    - ``bed_center`` (str): Bed centre as ``"X,Y"`` (computed from
      ``bed_shape``).
    - ``printer_model`` (str): Printer model identifier.
    - ``filament_type`` (str): Filament type (e.g. ``"PETG"``, ``"PLA"``).

    Keys are omitted when the ``.ini`` file does not contain the relevant
    setting or the value cannot be parsed.

    Parameters
    ----------
    path : str
        Path to the PrusaSlicer ``.ini`` config file.

    Returns
    -------
    dict
        Extracted settings.  Empty dict if the file cannot be read.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")

    # PrusaSlicer config exports may lack section headers.
    # configparser requires at least one section, so prepend a default.
    if not any(line.strip().startswith("[") for line in text.splitlines()):
        text = "[DEFAULT]\n" + text

    parser = configparser.RawConfigParser()
    parser.read_string(text)

    # Collect all key-value pairs across all sections into a flat dict.
    # Later sections override earlier ones (unlikely in practice).
    flat: Dict[str, str] = {}
    for section in parser.sections():
        flat.update(dict(parser[section]))
    # Also include DEFAULT section items.
    flat.update(dict(parser.defaults()))

    result: Dict[str, Any] = {}

    # --- Nozzle diameter ---
    if "nozzle_diameter" in flat:
        val = _parse_float(flat["nozzle_diameter"])
        if val is not None and val > 0:
            result["nozzle_diameter"] = val

    # --- Nozzle temperature (prefer 'temperature' over fallback) ---
    for key in ("temperature", "first_layer_temperature"):
        if key in flat:
            val = _parse_int(flat[key])
            if val is not None and val > 0:
                result["nozzle_temp"] = val
                break

    # --- Bed temperature ---
    for key in ("bed_temperature", "first_layer_bed_temperature"):
        if key in flat:
            val = _parse_int(flat[key])
            if val is not None and val >= 0:
                result["bed_temp"] = val
                break

    # --- Fan speed ---
    if "max_fan_speed" in flat:
        val = _parse_int(flat["max_fan_speed"])
        if val is not None and 0 <= val <= 100:
            result["fan_speed"] = val

    # --- Layer height ---
    if "layer_height" in flat:
        val = _parse_float(flat["layer_height"])
        if val is not None and val > 0:
            result["layer_height"] = val

    # --- Extrusion width ---
    if "extrusion_width" in flat:
        val = _parse_extrusion_width(flat["extrusion_width"])
        if val is not None:
            result["extrusion_width"] = val

    # --- Bed shape → bed centre ---
    if "bed_shape" in flat:
        centre = _parse_bed_shape(flat["bed_shape"])
        if centre is not None:
            result["bed_center"] = centre

    # --- Printer model ---
    if "printer_model" in flat:
        val = flat["printer_model"].strip()
        if val:
            result["printer_model"] = val

    # --- Filament type ---
    if "filament_type" in flat:
        val = _first_value(flat["filament_type"]).strip()
        if val:
            result["filament_type"] = val

    return result
