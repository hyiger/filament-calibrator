"""TOML configuration file support for filament-calibrator.

Lookup order (first found wins):
1. Explicit ``--config <path>`` CLI flag
2. ``./filament-calibrator.toml`` (project-local)
3. ``~/filament-calibrator.toml`` (home directory)
4. ``~/.config/filament-calibrator/config.toml`` (XDG user config)
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

#: Keys that are valid in the config file.
CONFIG_KEYS: frozenset[str] = frozenset({
    "printer-url",
    "api-key",
    "prusaslicer-path",
    "config-ini",
    "filament-type",
    "output-dir",
    "bed-center",
    "nozzle-size",
    "nozzle-high-flow",
    "nozzle-hardened",
    "printer",
    "nozzle-temp",
    "bed-temp",
    "fan-speed",
})

#: Expected types for each config key.  Used by :func:`load_config`
#: to validate TOML values and emit warnings for mismatched types.
_EXPECTED_TYPES: Dict[str, type] = {
    "printer-url": str,
    "api-key": str,
    "prusaslicer-path": str,
    "config-ini": str,
    "filament-type": str,
    "output-dir": str,
    "bed-center": str,
    "nozzle-size": float,
    "nozzle-high-flow": bool,
    "nozzle-hardened": bool,
    "printer": str,
    "nozzle-temp": int,
    "bed-temp": int,
    "fan-speed": int,
}

#: Map TOML key names (hyphenated) to argparse attribute names (underscored).
_KEY_TO_ATTR: Dict[str, str] = {k: k.replace("-", "_") for k in CONFIG_KEYS}


def _find_config_path(explicit: Optional[str] = None) -> Optional[Path]:
    """Return the first config file that exists, or *None*.

    Lookup order:
    1. *explicit* path (from ``--config``)
    2. ``./filament-calibrator.toml``
    3. ``~/filament-calibrator.toml``
    4. ``~/.config/filament-calibrator/config.toml``
    """
    if explicit is not None:
        p = Path(explicit)
        if not p.is_file():
            sys.exit(f"error: config file not found: {explicit}")
        return p

    local = Path("filament-calibrator.toml")
    if local.is_file():
        return local

    home = Path.home() / "filament-calibrator.toml"
    if home.is_file():
        return home

    xdg = Path.home() / ".config" / "filament-calibrator" / "config.toml"
    if xdg.is_file():
        return xdg

    return None


def load_config(explicit_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from the first TOML file found.

    Returns a dict mapping argparse attribute names (underscored) to their
    values.  Unknown keys emit a warning and are skipped.  Returns an empty
    dict when no config file is found.
    """
    path = _find_config_path(explicit_path)
    if path is None:
        return {}

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    result: Dict[str, Any] = {}
    for key, value in raw.items():
        if key not in CONFIG_KEYS:
            warnings.warn(
                f"unknown config key {key!r} in {path} (ignored)",
                stacklevel=2,
            )
            continue
        expected = _EXPECTED_TYPES.get(key)
        if expected is not None and not isinstance(value, expected):
            # Accept int where float is expected (TOML ``nozzle-size = 1``),
            # but reject bool (which is a subclass of int in Python).
            if expected is float and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            else:
                warnings.warn(
                    f"config key {key!r} in {path} has type "
                    f"{type(value).__name__}, expected {expected.__name__} "
                    f"(ignored)",
                    stacklevel=2,
                )
                continue
        result[_KEY_TO_ATTR[key]] = value

    return result
