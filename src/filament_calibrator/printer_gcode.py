"""Printer-specific start/end G-code templates for Prusa printers.

Each supported printer has a start and end G-code template with
``{placeholder}`` variables that are rendered with actual values at
generation time.  Templates are sourced from the PrusaSlicer default
profiles for each printer model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import gcode_lib as gl


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Printers with G-code templates.  These names match the keys in
#: ``gcode_lib.PRINTER_PRESETS`` (after alias resolution).
KNOWN_PRINTERS: Tuple[str, ...] = ("COREONE", "COREONEL", "MK4S", "MINI", "XL")

#: Map gcode-lib preset names to template names when they differ.
_PRINTER_ALIASES: Dict[str, str] = {
    "MK4": "MK4S",
}

#: Reverse map: template names → gcode-lib preset names (for bed lookups).
_PRESET_ALIASES: Dict[str, str] = {v: k for k, v in _PRINTER_ALIASES.items()}

#: Default MBL (mesh bed leveling) nozzle temperature.
MBL_TEMP: int = 170


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PrinterGCode:
    """Start and end G-code templates for a single printer model."""
    start: str
    end: str


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_COREONE_START = """\
M17 ; enable steppers
M862.1 P{nozzle_dia} ; nozzle check
M862.3 P "COREONE" ; printer model check
M862.5 P2 ; g-code level check
M862.6 P"Input shaper" ; FW feature check
M115 U6.4.0+11974
M555 X{m555_x} Y{m555_y} W{m555_w} H{m555_h}
G90 ; use absolute coordinates
M83 ; extruder relative mode
M140 S{bed_temp} ; set bed temp
M109 R{mbl_temp} ; preheat nozzle to no-ooze temp for bed leveling
M84 E ; turn off E motor
G28 ; home all without mesh bed level
M104 S100 ; set idle temp
M190 R{bed_temp} ; wait for bed temp
{cool_fan}
G0 Z40 F10000
M104 S100 ; keep idle temp
M190 R{bed_temp} ; wait for bed temp (confirm after Z move)
M107
G29 G ; absorb heat
M109 R{mbl_temp} ; wait for MBL temp
M302 S155 ; lower cold extrusion limit to 155 C
G1 E-2 F2400 ; retraction
M84 E ; turn off E motor
G29 P9 X208 Y-2.5 W32 H4
;
; MBL
;
M84 E ; turn off E motor
G29 P1 ; invalidate mbl and probe print area
G29 P1 X150 Y0 W100 H20 C ; probe near purge place
G29 P3.2 ; interpolate mbl probes
G29 P3.13 ; extrapolate mbl outside probe area
G29 A ; activate mbl
; prepare for purge
M104 S{hotend_temp}
G0 X249 Y-2.5 Z15 F4800 ; move away and ready for the purge
M109 S{hotend_temp}
G92 E0
M569 S0 E ; set spreadcycle mode for extruder
M591 S0 ; disable stuck filament detection
;
; Purge line
;
G92 E0 ; reset extruder position
G1 E2 F2400 ; deretraction after the initial one
G0 E5 X235 Z0.2 F500 ; purge
G0 X225 E4 F500 ; purge
G0 X215 E4 F650 ; purge
G0 X205 E4 F800 ; purge
G0 X202 Z0.05 F8000 ; wipe, move close to the bed
G0 X199 Z0.2 F8000 ; wipe, move away from the bed
M591 R ; restore stuck filament detection
G92 E0
M221 S100 ; set flow to 100%"""

_COREONE_END = """\
G1 Z{park_z} F720 ; move print head up
M104 S0 ; turn off hotend
M140 S0 ; turn off heatbed
M141 S0 ; disable chamber temp control
M107 ; turn off fan
G1 X242 Y211 F10200 ; park
G4 ; wait
M572 S0 ; reset pressure advance (ignored on Marlin)
M900 K0 ; reset Linear Advance
M84 X Y E ; disable motors
; max_layer_z = {max_layer_z}"""

_COREONEL_START = """\
M17 ; enable steppers
M862.1 P{nozzle_dia} ; nozzle check
M862.3 P "COREONEL" ; printer model check
M862.5 P2 ; g-code level check
M862.6 P"Input shaper" ; FW feature check
M115 U6.5.1+12574
M555 X{m555_x} Y{m555_y} W{m555_w} H{m555_h}
G90 ; use absolute coordinates
M83 ; extruder relative mode
M140 S{bed_temp} ; set bed temp
M106 P5 R A125 B10 ; turn on bed fans with fade
M109 R{mbl_temp} ; preheat nozzle to no-ooze temp for bed leveling
M84 E ; turn off E motor
G28 Q ; home all without mesh bed level
G1 Z20 F720 ; lift bed to optimal bed fan height
M141 S0 ; set nominal chamber temp
{cool_fan}
M190 R{bed_temp} ; wait for bed temp
M107
M109 R{mbl_temp} ; wait for MBL temp
M302 S155 ; lower cold extrusion limit to 155 C
G1 E-2 F2400 ; retraction
M84 E ; turn off E motor
G29 P9 X208 Y-2.5 W32 H4
;
; MBL
;
M84 E ; turn off E motor
G29 P1 ; invalidate mbl and probe print area
G29 P1 X150 Y0 W100 H20 C ; probe near purge place
G29 P3.2 ; interpolate mbl probes
G29 P3.13 ; extrapolate mbl outside probe area
G29 A ; activate mbl
; prepare for purge
M104 S{hotend_temp}
G0 X249 Y-2.5 Z15 F4800 ; move away and ready for the purge
M109 S{hotend_temp}
G92 E0
M569 S0 E ; set spreadcycle mode for extruder
M591 S0 ; disable stuck filament detection
;
; Purge line
;
G92 E0 ; reset extruder position
G1 E2 F2400 ; deretraction after the initial one
G0 E5 X235 Z0.2 F500 ; purge
G0 X225 E4 F500 ; purge
G0 X215 E4 F650 ; purge
G0 X205 E4 F800 ; purge
G0 X202 Z0.05 F8000 ; wipe, move close to the bed
G0 X199 Z0.2 F8000 ; wipe, move away from the bed
M591 R ; restore stuck filament detection
G92 E0
M221 S100 ; set flow to 100%"""

_COREONEL_END = """\
G1 Z{park_z} F720 ; move print head up
M104 S0 ; turn off hotend
M140 S0 ; turn off heatbed
M141 S0 ; disable chamber temp control
M107 ; turn off fan
M107 P5 ; turn off bed fans
G1 X290 Y295 F10200 ; park
G4 ; wait
M572 S0 ; reset pressure advance (ignored on Marlin)
M900 K0 ; reset Linear Advance
M84 X Y E ; disable motors
; max_layer_z = {max_layer_z}"""

_MK4S_START = """\
M17 ; enable steppers
M862.1 P{nozzle_dia} ; nozzle check
M862.3 P "MK4S" ; printer model check
M862.5 P2 ; g-code level check
M862.6 P"Input shaper" ; FW feature check
M115 U6.4.0+11974
M555 X{m555_x} Y{m555_y} W{m555_w} H{m555_h}
G90 ; use absolute coordinates
M83 ; extruder relative mode
M140 S{bed_temp} ; set bed temp
M104 S{mbl_temp} ; set extruder temp for bed leveling
M109 R{mbl_temp} ; wait for bed leveling temp
M84 E ; turn off E motor
G28 ; home all without mesh bed level
G1 X42 Y-4 Z5 F4800
M302 S155 ; lower cold extrusion limit to 155 C
G1 E-2 F2400 ; retraction
M84 E ; turn off E motor
G29 P9 X10 Y-4 W32 H4
{cool_fan}
G0 Z40 F10000
M190 S{bed_temp} ; wait for bed temp
M107
;
; MBL
;
M84 E ; turn off E motor
G29 P1 ; invalidate mbl and probe print area
G29 P1 X0 Y0 W50 H20 C ; probe near purge place
G29 P3.2 ; interpolate mbl probes
G29 P3.13 ; extrapolate mbl outside probe area
G29 A ; activate mbl
; prepare for purge
M104 S{hotend_temp}
G0 X0 Y-4 Z15 F4800 ; move away and ready for the purge
M109 S{hotend_temp}
G92 E0
M569 S0 E ; set spreadcycle mode for extruder
;
; Purge line
;
G92 E0 ; reset extruder position
G1 E2 F2400 ; deretraction after the initial one
G0 E7 X15 Z0.2 F500 ; purge
G0 X25 E4 F500 ; purge
G0 X35 E4 F650 ; purge
G0 X45 E4 F800 ; purge
G0 X48 Z0.05 F8000 ; wipe, move close to the bed
G0 X51 Z0.2 F8000 ; wipe, move away from the bed
G92 E0
M221 S100 ; set flow to 100%"""

_MK4S_END = """\
G1 Z{park_z} F720 ; move print head up
M104 S0 ; turn off hotend
M140 S0 ; turn off heatbed
M107 ; turn off fan
G1 X241 Y170 F3600 ; park
G4 ; wait
M572 S0 ; reset pressure advance (ignored on Marlin)
M900 K0 ; reset Linear Advance
M593 X T2 F0 ; disable input shaping X
M593 Y T2 F0 ; disable input shaping Y
M84 X Y E ; disable motors
; max_layer_z = {max_layer_z}"""

_MINI_START = """\
M862.3 P "MINI" ; printer model check
M862.1 P{nozzle_dia} ; nozzle check
M862.5 P2 ; g-code level check
M862.6 P"Input shaper" ; FW feature check
M115 U6.4.0+11974
G90 ; use absolute coordinates
M83 ; extruder relative mode
M104 S{mbl_temp} ; set extruder temp for bed leveling
M140 S{bed_temp} ; set bed temp
M109 R{mbl_temp} ; wait for bed leveling temp
M190 S{bed_temp} ; wait for bed temp
M569 S1 X Y ; set stealthchop for X Y
M204 T1250 ; set travel acceleration
G28 ; home all without mesh bed level
G29 ; mesh bed leveling
M104 S{hotend_temp} ; set extruder temp
G92 E0
G1 X0 Y-2 Z3 F2400
M109 S{hotend_temp} ; wait for extruder temp
;
; Intro line
;
G1 X10 Z0.2 F1000
G1 X70 E8 F900
G1 X140 E10 F700
G92 E0
M569 S0 X Y ; set spreadcycle for X Y
M204 T1250 ; restore travel acceleration
M572 W0.06 ; set pressure advance smooth time
M221 S95 ; set flow"""

_MINI_END = """\
G1 Z{park_z} F720 ; move print head up
M104 S0 ; turn off hotend
M140 S0 ; turn off heatbed
M107 ; turn off fan
G1 X90 Y170 F3600 ; park
G4 ; wait
M900 K0 ; reset Linear Advance
M84 X Y E ; disable motors
; max_layer_z = {max_layer_z}"""

_XL_START = """\
M17 ; enable steppers
M862.3 P "XL" ; printer model check
M862.5 P2 ; g-code level check
M862.6 P"Input shaper" ; FW feature check
M115 U6.2.6+8948
G90 ; use absolute coordinates
M83 ; extruder relative mode
M555 X{m555_x} Y{m555_y} W{m555_w} H{m555_h}
M862.1 P{nozzle_dia} ; nozzle check
M140 S{bed_temp} ; set bed temp
M104 S{mbl_temp} ; set extruder temp for bed leveling
G28 XY ; home carriage
M109 R{mbl_temp} ; wait for bed leveling temp
M84 E ; turn off E motor
G28 Z ; home Z
M104 S70 ; set idle temp
M190 S{bed_temp} ; wait for bed temp
G29 G ; absorb heat
M109 R{mbl_temp} ; wait for MBL temp
; move to nozzle cleanup area
G1 X30 Y-8 Z5 F4800
M302 S155 ; lower cold extrusion limit to 155 C
G1 E-2 F2400 ; retraction
M84 E ; turn off E motor
G29 P9 X30 Y-8 W32 H7
G0 Z10 F480 ; move away in Z
M106 S100 ; cool nozzle
M107 ; stop cooling fan
;
; MBL
;
M84 E ; turn off E motor
G29 P1 ; invalidate mbl and probe print area
G29 P1 X30 Y0 W50 H20 C ; probe near purge place
G29 P3.2 ; interpolate mbl probes
G29 P3.13 ; extrapolate mbl outside probe area
G29 A ; activate mbl
M104 S{hotend_temp} ; set extruder temp
G1 Z10 F720 ; move away in Z
G0 X30 Y-8 F6000 ; move next to the sheet
M109 S{hotend_temp} ; wait for extruder temp
M591 S0 ; disable stuck filament detection
;
; Purge line
;
G92 E0 ; reset extruder position
G0 X30 Y-8 ; move close to the sheet edge
G1 E2 F2400 ; deretraction after the initial one
G0 E10 X40 Z0.2 F500 ; purge
G0 X70 E9 F800 ; purge
G0 X73 Z0.05 F8000 ; wipe, move close to the bed
G0 X76 Z0.2 F8000 ; wipe, move away from the bed
M591 R ; restore stuck filament detection
G92 E0 ; reset extruder position"""

_XL_END = """\
G1 Z{park_z} F720 ; move bed down
M104 S0 ; turn off hotend
M140 S0 ; turn off heatbed
M107 ; turn off fan
G1 X6 Y350 F6000 ; park
G4 ; wait
M900 K0 ; reset Linear Advance
M142 S36 ; reset heatbreak target temp
M221 S100 ; reset flow percentage
M84 ; disable motors
; max_layer_z = {max_layer_z}"""


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: Dict[str, PrinterGCode] = {
    "COREONE": PrinterGCode(start=_COREONE_START, end=_COREONE_END),
    "COREONEL": PrinterGCode(start=_COREONEL_START, end=_COREONEL_END),
    "MK4S": PrinterGCode(start=_MK4S_START, end=_MK4S_END),
    "MINI": PrinterGCode(start=_MINI_START, end=_MINI_END),
    "XL": PrinterGCode(start=_XL_START, end=_XL_END),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_printer(name: str) -> str:
    """Normalise a printer name and validate it has a template.

    Accepts case-insensitive names and applies aliases
    (e.g. ``"mk4"`` → ``"MK4S"``).

    Returns the canonical (upper-case) template key, or calls
    :func:`sys.exit` if the name is unknown.
    """
    import sys

    upper = name.upper()
    resolved = _PRINTER_ALIASES.get(upper, upper)
    if resolved not in _TEMPLATES:
        names = ", ".join(sorted(_TEMPLATES.keys()))
        sys.exit(
            f"error: unknown printer {name!r}. "
            f"Available printers: {names}"
        )
    return resolved


def _lookup_preset(printer: str) -> dict | None:
    """Look up a printer preset, trying direct name and alias."""
    preset = gl.PRINTER_PRESETS.get(printer)
    if preset is None:
        preset = gl.PRINTER_PRESETS.get(
            _PRESET_ALIASES.get(printer, printer)
        )
    return preset


def compute_bed_center(printer: str) -> str:
    """Return ``"X,Y"`` bed centre string from ``PRINTER_PRESETS``.

    Falls back to ``"125,110"`` if the printer is not in presets.
    """
    preset = _lookup_preset(printer)
    if preset is None:
        return "125,110"
    cx = int(preset["bed_x"] / 2)
    cy = int(preset["bed_y"] / 2)
    return f"{cx},{cy}"


def compute_bed_shape(printer: str) -> str:
    """Return PrusaSlicer ``--bed-shape`` string from ``PRINTER_PRESETS``.

    Falls back to ``"0x0,250x0,250x220,0x220"`` if the printer is not
    in presets.
    """
    preset = _lookup_preset(printer)
    if preset is None:
        return "0x0,250x0,250x220,0x220"
    bx = int(preset["bed_x"])
    by = int(preset["bed_y"])
    return f"0x0,{bx}x0,{bx}x{by},0x{by}"


def compute_m555(
    bed_center: str,
    model_width: float,
    model_depth: float,
) -> Dict[str, int]:
    """Compute M555 bounding-box parameters for the print area hint.

    The model is assumed to be centred at *bed_center*.

    Returns a dict with keys ``m555_x``, ``m555_y``, ``m555_w``, ``m555_h``.
    """
    parts = bed_center.split(",")
    cx, cy = float(parts[0]), float(parts[1])
    x = int(cx - model_width / 2)
    y = int(cy - model_depth / 2)
    return {
        "m555_x": x,
        "m555_y": y,
        "m555_w": int(model_width),
        "m555_h": int(model_depth),
    }


def render_start_gcode(
    printer: str,
    *,
    nozzle_dia: float,
    bed_temp: int,
    hotend_temp: int,
    bed_center: str,
    model_width: float,
    model_depth: float,
    cool_fan: bool = True,
) -> str:
    """Render the start G-code template for *printer*.

    Parameters
    ----------
    printer:      Canonical printer name (from :func:`resolve_printer`).
    nozzle_dia:   Nozzle diameter in mm.
    bed_temp:     Bed temperature in deg C.
    hotend_temp:  Hotend temperature in deg C.
    bed_center:   Bed centre as ``"X,Y"`` string.
    model_width:  Model width in mm (for M555).
    model_depth:  Model depth in mm (for M555).
    cool_fan:     Whether to enable cooling fan during MBL (True for
                  PLA-like filaments, False for materials needing an
                  enclosure).
    """
    template = _TEMPLATES[printer].start
    m555 = compute_m555(bed_center, model_width, model_depth)
    mbl_temp = min(hotend_temp, MBL_TEMP)
    cool_fan_cmd = "M106 S255" if cool_fan else ""

    return template.format(
        nozzle_dia=nozzle_dia,
        bed_temp=bed_temp,
        hotend_temp=hotend_temp,
        mbl_temp=mbl_temp,
        cool_fan=cool_fan_cmd,
        **m555,
    )


def render_end_gcode(
    printer: str,
    *,
    max_layer_z: float,
) -> str:
    """Render the end G-code template for *printer*.

    Parameters
    ----------
    printer:       Canonical printer name (from :func:`resolve_printer`).
    max_layer_z:   Final Z height of the print in mm.
    """
    template = _TEMPLATES[printer].end
    # Park Z: at least max_layer_z + 10, capped at printer's max Z.
    preset = gl.PRINTER_PRESETS.get(
        _PRINTER_ALIASES.get(printer, printer)
    )
    if preset is None:
        preset = gl.PRINTER_PRESETS.get(printer)
    max_z = float(preset["max_z"]) if preset is not None else 250.0
    park_z = min(max_layer_z + 10.0, max_z)

    return template.format(
        park_z=f"{park_z:.1f}",
        max_layer_z=f"{max_layer_z:.2f}",
    )
