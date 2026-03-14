"""Shared test helpers for filament-calibrator tests."""
from __future__ import annotations

from typing import List

import gcode_lib as gl


def parse_gcode(text: str) -> List[gl.GCodeLine]:
    """Parse a multi-line G-code string into a list of GCodeLine objects."""
    return gl.parse_lines(text)


def raw_texts(lines: List[gl.GCodeLine]) -> List[str]:
    """Extract raw text strings from a list of GCodeLine objects."""
    return [line.raw for line in lines]
