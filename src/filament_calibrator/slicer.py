"""PrusaSlicer orchestration for calibration model slicing.

Wraps gcode-lib's PrusaSlicer CLI helpers with sensible defaults for
temperature tower prints, volumetric flow specimens, and pressure advance
calibration towers.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import gcode_lib as gl

# ---------------------------------------------------------------------------
# Default slicer settings (used when no .ini config is provided)
# ---------------------------------------------------------------------------

DEFAULT_SLICER_ARGS: Dict[str, str] = {
    "layer-height": "0.2",
    "first-layer-height": "0.2",
    "perimeters": "2",
    "top-solid-layers": "4",
    "bottom-solid-layers": "3",
    "fill-density": "15%",
    "skirts": "1",
}

# Default bed centre for Prusa printers (250 × 220 mm bed).
# Used with PrusaSlicer's --center flag to place the model on the bed.
DEFAULT_BED_CENTER: str = "125,110"

# Thumbnail sizes embedded in G-code for LCD preview on Prusa printers.
# 16×16 provides a small icon; 220×124 matches the MK3S LCD resolution.
# PrusaSlicer 2.9+ requires the format suffix (e.g. /PNG) in each size spec.
DEFAULT_THUMBNAILS: str = "16x16/PNG,220x124/PNG"
DEFAULT_BED_SHAPE: str = "0x0,250x0,250x220,0x220"
"""Slicer defaults applied when no ``--config-ini`` is supplied.

These produce a reasonable temp tower slice with 0.2mm layers, 2 perimeters,
and 15% infill — enough structure to evaluate temperature quality without
wasting filament.  Support material is disabled by PrusaSlicer's default.
"""

# Slicer settings for spiral-vase flow specimen (used when no .ini provided).
VASE_MODE_SLICER_ARGS: Dict[str, str] = {
    "first-layer-height": "0.2",
    "perimeters": "1",
    "top-solid-layers": "0",
    "fill-density": "0%",
    "skirts": "0",
}
"""Slicer defaults for vase-mode flow specimens.

Single perimeter, no infill, no top layers — spiral-vase mode handles the
rest.  ``layer-height`` and ``extrusion-width`` are passed explicitly by
:func:`slice_flow_specimen` so they are **not** included here.
"""

# Slicer settings for PA calibration tower (used when no .ini provided).
PA_SLICER_ARGS: Dict[str, str] = {
    "first-layer-height": "0.2",
    "perimeters": "2",
    "top-solid-layers": "0",
    "bottom-solid-layers": "0",
    "fill-density": "0%",
    "skirts": "1",
}
"""Slicer defaults for pressure advance calibration towers.

Two perimeters for inner/outer wall interaction at corners, zero infill
(hollow interior handled by the shell geometry), zero top/bottom solid
layers.  ``layer-height`` and ``extrusion-width`` are passed explicitly
by :func:`slice_pa_specimen` so they are **not** included here.
"""

# Slicer settings for PA diamond pattern (used when no .ini provided).
PA_PATTERN_SLICER_ARGS: Dict[str, str] = {
    "first-layer-height": "0.2",
    "top-solid-layers": "0",
    "bottom-solid-layers": "0",
    "fill-density": "0%",
    "skirts": "1",
}
"""Slicer defaults for PA diamond pattern calibration prints.

Same as :data:`PA_SLICER_ARGS` but ``perimeters`` is *not* included —
it is passed explicitly by :func:`slice_pa_pattern` so the user can
control the number of concentric walls (``--wall-count``).
"""

# Slicer settings for EM calibration cube (used when no .ini provided).
EM_SLICER_ARGS: Dict[str, str] = {
    "first-layer-height": "0.2",
    "perimeters": "1",
    "top-solid-layers": "0",
    "fill-density": "0%",
    "skirts": "0",
}
"""Slicer defaults for extrusion multiplier calibration cubes.

Single perimeter, no infill, no top/bottom layers — spiral-vase mode
with classic perimeter generation.  ``layer-height`` and
``extrusion-width`` are passed explicitly by :func:`slice_em_specimen`
so they are **not** included here.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def slice_tower(
    stl_path: str,
    output_gcode_path: str,
    config_ini: Optional[str] = None,
    prusaslicer_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    bed_temp: Optional[int] = None,
    fan_speed: Optional[int] = None,
    nozzle_temp: Optional[int] = None,
    bed_center: Optional[str] = None,
    bed_shape: Optional[str] = None,
    nozzle_diameter: Optional[float] = None,
    layer_height: Optional[float] = None,
    extrusion_width: Optional[float] = None,
    printer_model: Optional[str] = None,
    binary_gcode: bool = True,
) -> gl.RunResult:
    """Slice the temperature tower STL into G-code.

    If *config_ini* is ``None``, :data:`DEFAULT_SLICER_ARGS` are passed as
    ``--key value`` CLI arguments to PrusaSlicer, together with
    *nozzle_temp*, *bed_temp*, and *fan_speed* when provided.  When
    *config_ini* is set the ``.ini`` profile is loaded via ``--load``
    and the temperature / fan args are still appended (they override
    ``.ini`` values).

    Parameters
    ----------
    stl_path:          Path to the input ``.stl`` file.
    output_gcode_path: Desired output G-code path.
    config_ini:        Optional PrusaSlicer ``.ini`` config file path.
    prusaslicer_path:  Explicit path to PrusaSlicer executable (or ``None``
                       to auto-detect).
    extra_args:        Additional raw CLI arguments.
    bed_temp:          Bed temperature in °C (passed as
                       ``--bed-temperature``).
    fan_speed:         Fan speed 0–100 % (passed as
                       ``--max-fan-speed`` and ``--min-fan-speed``).
    nozzle_temp:       Nozzle temperature in °C (passed as
                       ``--temperature`` and ``--first-layer-temperature``).
                       Should be the tower's *start_temp* so PrusaSlicer's
                       start G-code heats to the correct initial temperature.
    bed_center:        Bed centre as ``"X,Y"`` (e.g. ``"125,110"``).
                       Passed as ``--center`` so PrusaSlicer places the
                       model in the middle of the bed.  Defaults to
                       :data:`DEFAULT_BED_CENTER` when ``None``.
    bed_shape:         Bed shape as PrusaSlicer ``--bed-shape`` string
                       (e.g. ``"0x0,250x0,250x220,0x220"``).  Defaults to
                       :data:`DEFAULT_BED_SHAPE` when ``None``.
    nozzle_diameter:   Nozzle diameter in mm (passed as
                       ``--nozzle-diameter``).
    layer_height:      Layer height in mm.  When provided and *config_ini*
                       is ``None``, overrides the default from
                       :data:`DEFAULT_SLICER_ARGS`.
    extrusion_width:   Extrusion width in mm (passed as
                       ``--extrusion-width``).
    printer_model:     Printer model identifier (e.g. ``"COREONE"``)
                       passed as ``--printer-model`` so PrusaSlicer embeds
                       it in bgcode metadata for G-code Viewer bed display.

    Returns
    -------
    gcode_lib.RunResult
        Exit code, stdout, and stderr from PrusaSlicer.

    Raises
    ------
    FileNotFoundError
        If PrusaSlicer cannot be found.
    """
    exe = gl.find_prusaslicer_executable(explicit_path=prusaslicer_path)

    cli_extra: List[str] = [
        f"--center={bed_center or DEFAULT_BED_CENTER}",
        f"--bed-shape={bed_shape or DEFAULT_BED_SHAPE}",
        f"--thumbnails={DEFAULT_THUMBNAILS}",
    ]
    if binary_gcode:
        cli_extra.append("--binary-gcode")
    if config_ini is None:
        # When caller provides layer_height, skip the dict defaults for
        # layer-height and first-layer-height so they aren't duplicated.
        skip = {"layer-height", "first-layer-height"} if layer_height is not None else set()
        for key, val in DEFAULT_SLICER_ARGS.items():
            if key not in skip:
                cli_extra.append(f"--{key}={val}")
        if layer_height is not None:
            cli_extra.append(f"--layer-height={layer_height}")
            cli_extra.append(f"--first-layer-height={layer_height}")

    if nozzle_diameter is not None:
        cli_extra.append(f"--nozzle-diameter={nozzle_diameter}")
    if extrusion_width is not None:
        cli_extra.append(f"--extrusion-width={extrusion_width}")

    if nozzle_temp is not None:
        cli_extra.append(f"--temperature={nozzle_temp}")
        cli_extra.append(f"--first-layer-temperature={nozzle_temp}")
    if bed_temp is not None:
        cli_extra.append(f"--bed-temperature={bed_temp}")
        cli_extra.append(f"--first-layer-bed-temperature={bed_temp}")
    if fan_speed is not None:
        cli_extra.append(f"--max-fan-speed={fan_speed}")
        cli_extra.append(f"--min-fan-speed={fan_speed}")

    if printer_model is not None:
        cli_extra.append(f"--printer-model={printer_model}")

    if extra_args:
        cli_extra.extend(extra_args)

    req = gl.SliceRequest(
        input_path=stl_path,
        output_path=output_gcode_path,
        config_ini=config_ini,
        extra_args=cli_extra,
    )
    return gl.slice_model(exe, req)


def slice_flow_specimen(
    stl_path: str,
    output_gcode_path: str,
    layer_height: float = 0.2,
    extrusion_width: float = 0.45,
    config_ini: Optional[str] = None,
    prusaslicer_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    nozzle_temp: Optional[int] = None,
    bed_temp: Optional[int] = None,
    fan_speed: Optional[int] = None,
    bed_center: Optional[str] = None,
    bed_shape: Optional[str] = None,
    nozzle_diameter: Optional[float] = None,
    printer_model: Optional[str] = None,
    binary_gcode: bool = True,
) -> gl.RunResult:
    """Slice a flow-rate specimen STL in spiral-vase mode.

    Always enables ``--spiral-vase``.  When *config_ini* is ``None``,
    :data:`VASE_MODE_SLICER_ARGS` are applied together with the explicit
    *layer_height* and *extrusion_width*.

    Parameters
    ----------
    stl_path:          Path to the input ``.stl`` file.
    output_gcode_path: Desired output G-code path.
    layer_height:      Layer height in mm (default 0.2).
    extrusion_width:   Extrusion width in mm (default 0.45).
    config_ini:        Optional PrusaSlicer ``.ini`` config file path.
    prusaslicer_path:  Explicit path to PrusaSlicer executable (or ``None``
                       to auto-detect).
    extra_args:        Additional raw CLI arguments.
    nozzle_temp:       Nozzle temperature in °C.
    bed_temp:          Bed temperature in °C.
    fan_speed:         Fan speed 0–100 %.
    bed_center:        Bed centre as ``"X,Y"`` (defaults to
                       :data:`DEFAULT_BED_CENTER`).
    bed_shape:         Bed shape as PrusaSlicer ``--bed-shape`` string.
                       Defaults to :data:`DEFAULT_BED_SHAPE`.
    nozzle_diameter:   Nozzle diameter in mm (passed as
                       ``--nozzle-diameter``).
    printer_model:     Printer model identifier (e.g. ``"COREONE"``)
                       passed as ``--printer-model``.

    Returns
    -------
    gcode_lib.RunResult
        Exit code, stdout, and stderr from PrusaSlicer.

    Raises
    ------
    FileNotFoundError
        If PrusaSlicer cannot be found.
    """
    exe = gl.find_prusaslicer_executable(explicit_path=prusaslicer_path)

    cli_extra: List[str] = [
        f"--center={bed_center or DEFAULT_BED_CENTER}",
        f"--bed-shape={bed_shape or DEFAULT_BED_SHAPE}",
        f"--thumbnails={DEFAULT_THUMBNAILS}",
        "--spiral-vase",
        # Always override settings that are incompatible with or required
        # for spiral-vase mode, even when a user-supplied config.ini is
        # loaded (it may have supports, solid bottoms, or no brim).
        "--support-material=0",
        "--bottom-solid-layers=0",
        "--brim-width=5",
    ]
    if binary_gcode:
        cli_extra.append("--binary-gcode")

    if config_ini is None:
        for key, val in VASE_MODE_SLICER_ARGS.items():
            cli_extra.append(f"--{key}={val}")
        cli_extra.append(f"--layer-height={layer_height}")
        cli_extra.append(f"--extrusion-width={extrusion_width}")

    if nozzle_diameter is not None:
        cli_extra.append(f"--nozzle-diameter={nozzle_diameter}")
    if nozzle_temp is not None:
        cli_extra.append(f"--temperature={nozzle_temp}")
        cli_extra.append(f"--first-layer-temperature={nozzle_temp}")
    if bed_temp is not None:
        cli_extra.append(f"--bed-temperature={bed_temp}")
        cli_extra.append(f"--first-layer-bed-temperature={bed_temp}")
    if fan_speed is not None:
        cli_extra.append(f"--max-fan-speed={fan_speed}")
        cli_extra.append(f"--min-fan-speed={fan_speed}")

    if printer_model is not None:
        cli_extra.append(f"--printer-model={printer_model}")

    if extra_args:
        cli_extra.extend(extra_args)

    req = gl.SliceRequest(
        input_path=stl_path,
        output_path=output_gcode_path,
        config_ini=config_ini,
        extra_args=cli_extra,
    )
    return gl.slice_model(exe, req)


def slice_pa_specimen(
    stl_path: str,
    output_gcode_path: str,
    layer_height: float = 0.2,
    extrusion_width: float = 0.45,
    config_ini: Optional[str] = None,
    prusaslicer_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    nozzle_temp: Optional[int] = None,
    bed_temp: Optional[int] = None,
    fan_speed: Optional[int] = None,
    bed_center: Optional[str] = None,
    bed_shape: Optional[str] = None,
    nozzle_diameter: Optional[float] = None,
    start_gcode: Optional[str] = None,
    end_gcode: Optional[str] = None,
    printer_model: Optional[str] = None,
    binary_gcode: bool = True,
) -> gl.RunResult:
    """Slice a pressure advance calibration tower STL.

    When *config_ini* is ``None``, :data:`PA_SLICER_ARGS` are applied
    together with the explicit *layer_height* and *extrusion_width*.
    Uses 2 perimeters, 0% infill, and no top/bottom solid layers.

    Parameters
    ----------
    stl_path:          Path to the input ``.stl`` file.
    output_gcode_path: Desired output G-code path.
    layer_height:      Layer height in mm (default 0.2).
    extrusion_width:   Extrusion width in mm (default 0.45).
    config_ini:        Optional PrusaSlicer ``.ini`` config file path.
    prusaslicer_path:  Explicit path to PrusaSlicer executable.
    extra_args:        Additional raw CLI arguments.
    nozzle_temp:       Nozzle temperature in °C.
    bed_temp:          Bed temperature in °C.
    fan_speed:         Fan speed 0–100 %.
    bed_center:        Bed centre as ``"X,Y"`` (defaults to
                       :data:`DEFAULT_BED_CENTER`).
    bed_shape:         Bed shape as PrusaSlicer ``--bed-shape`` string.
                       Defaults to :data:`DEFAULT_BED_SHAPE`.
    nozzle_diameter:   Nozzle diameter in mm (passed as
                       ``--nozzle-diameter``).
    start_gcode:       Rendered start G-code string.  When provided,
                       passed to PrusaSlicer via ``--start-gcode``.
    end_gcode:         Rendered end G-code string.  When provided,
                       passed to PrusaSlicer via ``--end-gcode``.
    printer_model:     Printer model identifier (e.g. ``"COREONE"``)
                       passed as ``--printer-model``.

    Returns
    -------
    gcode_lib.RunResult

    Raises
    ------
    FileNotFoundError
        If PrusaSlicer cannot be found.
    """
    exe = gl.find_prusaslicer_executable(explicit_path=prusaslicer_path)

    cli_extra: List[str] = [
        f"--center={bed_center or DEFAULT_BED_CENTER}",
        f"--bed-shape={bed_shape or DEFAULT_BED_SHAPE}",
        f"--thumbnails={DEFAULT_THUMBNAILS}",
    ]
    if binary_gcode:
        cli_extra.append("--binary-gcode")

    if config_ini is None:
        for key, val in PA_SLICER_ARGS.items():
            cli_extra.append(f"--{key}={val}")
        cli_extra.append(f"--layer-height={layer_height}")
        cli_extra.append(f"--extrusion-width={extrusion_width}")

    if nozzle_diameter is not None:
        cli_extra.append(f"--nozzle-diameter={nozzle_diameter}")
    if nozzle_temp is not None:
        cli_extra.append(f"--temperature={nozzle_temp}")
        cli_extra.append(f"--first-layer-temperature={nozzle_temp}")
    if bed_temp is not None:
        cli_extra.append(f"--bed-temperature={bed_temp}")
        cli_extra.append(f"--first-layer-bed-temperature={bed_temp}")
    if fan_speed is not None:
        cli_extra.append(f"--max-fan-speed={fan_speed}")
        cli_extra.append(f"--min-fan-speed={fan_speed}")

    if printer_model is not None:
        cli_extra.append(f"--printer-model={printer_model}")

    if start_gcode is not None:
        escaped = start_gcode.replace("\n", "\\n")
        cli_extra.append(f"--start-gcode={escaped}")
    if end_gcode is not None:
        escaped = end_gcode.replace("\n", "\\n")
        cli_extra.append(f"--end-gcode={escaped}")

    if extra_args:
        cli_extra.extend(extra_args)

    req = gl.SliceRequest(
        input_path=stl_path,
        output_path=output_gcode_path,
        config_ini=config_ini,
        extra_args=cli_extra,
    )
    return gl.slice_model(exe, req)


def slice_pa_pattern(
    stl_path: str,
    output_gcode_path: str,
    layer_height: float = 0.2,
    extrusion_width: float = 0.45,
    perimeters: int = 3,
    config_ini: Optional[str] = None,
    prusaslicer_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    nozzle_temp: Optional[int] = None,
    bed_temp: Optional[int] = None,
    fan_speed: Optional[int] = None,
    bed_center: Optional[str] = None,
    bed_shape: Optional[str] = None,
    nozzle_diameter: Optional[float] = None,
    start_gcode: Optional[str] = None,
    end_gcode: Optional[str] = None,
    printer_model: Optional[str] = None,
    binary_gcode: bool = True,
) -> gl.RunResult:
    """Slice a PA diamond pattern STL.

    When *config_ini* is ``None``, :data:`PA_PATTERN_SLICER_ARGS` are
    applied together with the explicit *layer_height*, *extrusion_width*,
    and *perimeters*.

    Parameters
    ----------
    stl_path:          Path to the input ``.stl`` file.
    output_gcode_path: Desired output G-code path.
    layer_height:      Layer height in mm (default 0.2).
    extrusion_width:   Extrusion width in mm (default 0.45).
    perimeters:        Number of perimeters / concentric walls (default 3).
    config_ini:        Optional PrusaSlicer ``.ini`` config file path.
    prusaslicer_path:  Explicit path to PrusaSlicer executable.
    extra_args:        Additional raw CLI arguments.
    nozzle_temp:       Nozzle temperature in °C.
    bed_temp:          Bed temperature in °C.
    fan_speed:         Fan speed 0–100 %.
    bed_center:        Bed centre as ``"X,Y"``.
    bed_shape:         Bed shape as PrusaSlicer ``--bed-shape`` string.
    nozzle_diameter:   Nozzle diameter in mm.
    start_gcode:       Rendered start G-code string.
    end_gcode:         Rendered end G-code string.
    printer_model:     Printer model identifier.

    Returns
    -------
    gcode_lib.RunResult
    """
    exe = gl.find_prusaslicer_executable(explicit_path=prusaslicer_path)

    cli_extra: List[str] = [
        f"--center={bed_center or DEFAULT_BED_CENTER}",
        f"--bed-shape={bed_shape or DEFAULT_BED_SHAPE}",
        f"--thumbnails={DEFAULT_THUMBNAILS}",
    ]
    if binary_gcode:
        cli_extra.append("--binary-gcode")

    if config_ini is None:
        for key, val in PA_PATTERN_SLICER_ARGS.items():
            cli_extra.append(f"--{key}={val}")
        cli_extra.append(f"--perimeters={perimeters}")
        cli_extra.append(f"--layer-height={layer_height}")
        cli_extra.append(f"--extrusion-width={extrusion_width}")

    if nozzle_diameter is not None:
        cli_extra.append(f"--nozzle-diameter={nozzle_diameter}")
    if nozzle_temp is not None:
        cli_extra.append(f"--temperature={nozzle_temp}")
        cli_extra.append(f"--first-layer-temperature={nozzle_temp}")
    if bed_temp is not None:
        cli_extra.append(f"--bed-temperature={bed_temp}")
        cli_extra.append(f"--first-layer-bed-temperature={bed_temp}")
    if fan_speed is not None:
        cli_extra.append(f"--max-fan-speed={fan_speed}")
        cli_extra.append(f"--min-fan-speed={fan_speed}")

    if printer_model is not None:
        cli_extra.append(f"--printer-model={printer_model}")

    if start_gcode is not None:
        escaped = start_gcode.replace("\n", "\\n")
        cli_extra.append(f"--start-gcode={escaped}")
    if end_gcode is not None:
        escaped = end_gcode.replace("\n", "\\n")
        cli_extra.append(f"--end-gcode={escaped}")

    if extra_args:
        cli_extra.extend(extra_args)

    req = gl.SliceRequest(
        input_path=stl_path,
        output_path=output_gcode_path,
        config_ini=config_ini,
        extra_args=cli_extra,
    )
    return gl.slice_model(exe, req)


def slice_em_specimen(
    stl_path: str,
    output_gcode_path: str,
    layer_height: float = 0.2,
    extrusion_width: float = 0.45,
    config_ini: Optional[str] = None,
    prusaslicer_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    nozzle_temp: Optional[int] = None,
    bed_temp: Optional[int] = None,
    fan_speed: Optional[int] = None,
    bed_center: Optional[str] = None,
    bed_shape: Optional[str] = None,
    nozzle_diameter: Optional[float] = None,
    printer_model: Optional[str] = None,
    binary_gcode: bool = True,
) -> gl.RunResult:
    """Slice an extrusion multiplier calibration cube in vase mode.

    Always enables ``--spiral-vase`` and ``--perimeter-generator=classic``
    for a single classic-wall perimeter.  When *config_ini* is ``None``,
    :data:`EM_SLICER_ARGS` are applied together with the explicit
    *layer_height* and *extrusion_width*.

    Parameters
    ----------
    stl_path:          Path to the input ``.stl`` file.
    output_gcode_path: Desired output G-code path.
    layer_height:      Layer height in mm (default 0.2).
    extrusion_width:   Extrusion width in mm (default 0.45).
    config_ini:        Optional PrusaSlicer ``.ini`` config file path.
    prusaslicer_path:  Explicit path to PrusaSlicer executable (or ``None``
                       to auto-detect).
    extra_args:        Additional raw CLI arguments.
    nozzle_temp:       Nozzle temperature in °C.
    bed_temp:          Bed temperature in °C.
    fan_speed:         Fan speed 0–100 %.
    bed_center:        Bed centre as ``"X,Y"`` (defaults to
                       :data:`DEFAULT_BED_CENTER`).
    bed_shape:         Bed shape as PrusaSlicer ``--bed-shape`` string.
                       Defaults to :data:`DEFAULT_BED_SHAPE`.
    nozzle_diameter:   Nozzle diameter in mm (passed as
                       ``--nozzle-diameter``).
    printer_model:     Printer model identifier (e.g. ``"COREONE"``)
                       passed as ``--printer-model``.

    Returns
    -------
    gcode_lib.RunResult
        Exit code, stdout, and stderr from PrusaSlicer.

    Raises
    ------
    FileNotFoundError
        If PrusaSlicer cannot be found.
    """
    exe = gl.find_prusaslicer_executable(explicit_path=prusaslicer_path)

    cli_extra: List[str] = [
        f"--center={bed_center or DEFAULT_BED_CENTER}",
        f"--bed-shape={bed_shape or DEFAULT_BED_SHAPE}",
        f"--thumbnails={DEFAULT_THUMBNAILS}",
        "--spiral-vase",
        "--perimeter-generator=classic",
        # Always override settings that are incompatible with or required
        # for spiral-vase mode, even when a user-supplied config.ini is
        # loaded (it may have supports, solid bottoms, or no brim).
        "--support-material=0",
        "--bottom-solid-layers=0",
        "--brim-width=5",
    ]
    if binary_gcode:
        cli_extra.append("--binary-gcode")

    if config_ini is None:
        for key, val in EM_SLICER_ARGS.items():
            cli_extra.append(f"--{key}={val}")
        cli_extra.append(f"--layer-height={layer_height}")
        cli_extra.append(f"--extrusion-width={extrusion_width}")

    if nozzle_diameter is not None:
        cli_extra.append(f"--nozzle-diameter={nozzle_diameter}")
    if nozzle_temp is not None:
        cli_extra.append(f"--temperature={nozzle_temp}")
        cli_extra.append(f"--first-layer-temperature={nozzle_temp}")
    if bed_temp is not None:
        cli_extra.append(f"--bed-temperature={bed_temp}")
        cli_extra.append(f"--first-layer-bed-temperature={bed_temp}")
    if fan_speed is not None:
        cli_extra.append(f"--max-fan-speed={fan_speed}")
        cli_extra.append(f"--min-fan-speed={fan_speed}")

    if printer_model is not None:
        cli_extra.append(f"--printer-model={printer_model}")

    if extra_args:
        cli_extra.extend(extra_args)

    req = gl.SliceRequest(
        input_path=stl_path,
        output_path=output_gcode_path,
        config_ini=config_ini,
        extra_args=cli_extra,
    )
    return gl.slice_model(exe, req)


# Slicer settings for retraction calibration towers (used when no .ini provided).
RETRACTION_SLICER_ARGS: Dict[str, str] = {
    "first-layer-height": "0.2",
    "perimeters": "2",
    "top-solid-layers": "4",
    "bottom-solid-layers": "3",
    "fill-density": "15%",
    "skirts": "1",
}
"""Slicer defaults for retraction calibration towers.

Same structural settings as the temperature tower — 2 perimeters and 15%
infill provide enough stability for the two cylindrical pillars.
"""


def slice_retraction_specimen(
    stl_path: str,
    output_gcode_path: str,
    layer_height: float = 0.2,
    extrusion_width: float = 0.45,
    config_ini: Optional[str] = None,
    prusaslicer_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    nozzle_temp: Optional[int] = None,
    bed_temp: Optional[int] = None,
    fan_speed: Optional[int] = None,
    bed_center: Optional[str] = None,
    bed_shape: Optional[str] = None,
    nozzle_diameter: Optional[float] = None,
    start_gcode: Optional[str] = None,
    end_gcode: Optional[str] = None,
    printer_model: Optional[str] = None,
    binary_gcode: bool = True,
) -> gl.RunResult:
    """Slice a retraction calibration two-tower STL.

    Always enables ``--use-firmware-retraction`` so that PrusaSlicer emits
    ``G10``/``G11`` firmware retraction commands instead of explicit
    ``G1 E-`` moves.  This allows the firmware's retraction length (set
    by ``M207``) to be varied at each height level.

    When *config_ini* is ``None``, :data:`RETRACTION_SLICER_ARGS` are
    applied together with the explicit *layer_height* and *extrusion_width*.

    Parameters
    ----------
    stl_path:          Path to the input ``.stl`` file.
    output_gcode_path: Desired output G-code path.
    layer_height:      Layer height in mm (default 0.2).
    extrusion_width:   Extrusion width in mm (default 0.45).
    config_ini:        Optional PrusaSlicer ``.ini`` config file path.
    prusaslicer_path:  Explicit path to PrusaSlicer executable.
    extra_args:        Additional raw CLI arguments.
    nozzle_temp:       Nozzle temperature in °C.
    bed_temp:          Bed temperature in °C.
    fan_speed:         Fan speed 0–100 %.
    bed_center:        Bed centre as ``"X,Y"``.
    bed_shape:         Bed shape as PrusaSlicer ``--bed-shape`` string.
    nozzle_diameter:   Nozzle diameter in mm.
    start_gcode:       Rendered start G-code string.
    end_gcode:         Rendered end G-code string.
    printer_model:     Printer model identifier.

    Returns
    -------
    gcode_lib.RunResult

    Raises
    ------
    FileNotFoundError
        If PrusaSlicer cannot be found.
    """
    exe = gl.find_prusaslicer_executable(explicit_path=prusaslicer_path)

    cli_extra: List[str] = [
        f"--center={bed_center or DEFAULT_BED_CENTER}",
        f"--bed-shape={bed_shape or DEFAULT_BED_SHAPE}",
        f"--thumbnails={DEFAULT_THUMBNAILS}",
        # Always force firmware retraction so M207 controls retraction
        # length, even when a user-supplied config.ini is loaded.
        "--use-firmware-retraction",
    ]
    if binary_gcode:
        cli_extra.append("--binary-gcode")

    if config_ini is None:
        for key, val in RETRACTION_SLICER_ARGS.items():
            cli_extra.append(f"--{key}={val}")
        cli_extra.append(f"--layer-height={layer_height}")
        cli_extra.append(f"--extrusion-width={extrusion_width}")

    if nozzle_diameter is not None:
        cli_extra.append(f"--nozzle-diameter={nozzle_diameter}")
    if nozzle_temp is not None:
        cli_extra.append(f"--temperature={nozzle_temp}")
        cli_extra.append(f"--first-layer-temperature={nozzle_temp}")
    if bed_temp is not None:
        cli_extra.append(f"--bed-temperature={bed_temp}")
        cli_extra.append(f"--first-layer-bed-temperature={bed_temp}")
    if fan_speed is not None:
        cli_extra.append(f"--max-fan-speed={fan_speed}")
        cli_extra.append(f"--min-fan-speed={fan_speed}")

    if printer_model is not None:
        cli_extra.append(f"--printer-model={printer_model}")

    if start_gcode is not None:
        escaped = start_gcode.replace("\n", "\\n")
        cli_extra.append(f"--start-gcode={escaped}")
    if end_gcode is not None:
        escaped = end_gcode.replace("\n", "\\n")
        cli_extra.append(f"--end-gcode={escaped}")

    if extra_args:
        cli_extra.extend(extra_args)

    req = gl.SliceRequest(
        input_path=stl_path,
        output_path=output_gcode_path,
        config_ini=config_ini,
        extra_args=cli_extra,
    )
    return gl.slice_model(exe, req)
