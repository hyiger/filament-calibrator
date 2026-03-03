"""PrusaSlicer orchestration for temperature tower slicing.

Wraps gcode-lib's PrusaSlicer CLI helpers with sensible defaults for
temperature tower prints.
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
"""Slicer defaults applied when no ``--config-ini`` is supplied.

These produce a reasonable temp tower slice with 0.2mm layers, 2 perimeters,
and 15% infill — enough structure to evaluate temperature quality without
wasting filament.  Support material is disabled by PrusaSlicer's default.
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
                       Should be the tower's *high_temp* so PrusaSlicer's
                       start G-code heats to the correct initial temperature.

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

    cli_extra: List[str] = []
    if config_ini is None:
        for key, val in DEFAULT_SLICER_ARGS.items():
            cli_extra.append(f"--{key}={val}")

    if nozzle_temp is not None:
        cli_extra.append(f"--temperature={nozzle_temp}")
        cli_extra.append(f"--first-layer-temperature={nozzle_temp}")
    if bed_temp is not None:
        cli_extra.append(f"--bed-temperature={bed_temp}")
        cli_extra.append(f"--first-layer-bed-temperature={bed_temp}")
    if fan_speed is not None:
        cli_extra.append(f"--max-fan-speed={fan_speed}")
        cli_extra.append(f"--min-fan-speed={fan_speed}")

    if extra_args:
        cli_extra.extend(extra_args)

    req = gl.SliceRequest(
        input_path=stl_path,
        output_path=output_gcode_path,
        config_ini=config_ini,
        extra_args=cli_extra,
    )
    return gl.slice_model(exe, req)
