#!/usr/bin/env python3
"""Generate sample PNG images of each calibration specimen for documentation.

Usage:
    python docs/generate_images.py

Requires cadquery and gcode-lib (with VTK) to be installed.
Outputs PNGs to docs/images/.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import gcode_lib as gl

from filament_calibrator.em_model import EMCubeConfig, generate_em_cube_stl
from filament_calibrator.flow_model import (
    FlowSpecimenConfig,
    generate_flow_specimen_stl,
)
from filament_calibrator.model import TowerConfig, generate_tower_stl
from filament_calibrator.pa_model import PATowerConfig, generate_pa_tower_stl
from filament_calibrator.pa_pattern import (
    PAPatternConfig,
    generate_pa_pattern_stl,
)
from filament_calibrator.retraction_model import (
    RetractionTowerConfig,
    generate_retraction_tower_stl,
)

WIDTH = 800
HEIGHT = 600
IMAGES_DIR = Path(__file__).parent / "images"


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="doc-images-"))

    specimens: list[tuple[str, str]] = []

    # Temperature tower — 5 tiers
    stl = str(tmp / "temp_tower.stl")
    generate_tower_stl(TowerConfig(), stl)
    specimens.append((stl, "temperature-tower.png"))

    # Extrusion multiplier cube
    stl = str(tmp / "em_cube.stl")
    generate_em_cube_stl(EMCubeConfig(), stl)
    specimens.append((stl, "extrusion-multiplier.png"))

    # Volumetric flow specimen — 8 levels
    stl = str(tmp / "flow.stl")
    generate_flow_specimen_stl(FlowSpecimenConfig(num_levels=8), stl)
    specimens.append((stl, "volumetric-flow.png"))

    # Pressure advance tower — 10 levels
    stl = str(tmp / "pa_tower.stl")
    generate_pa_tower_stl(PATowerConfig(num_levels=10), stl)
    specimens.append((stl, "pressure-advance-tower.png"))

    # Pressure advance pattern — 5 chevrons
    stl = str(tmp / "pa_pattern.stl")
    generate_pa_pattern_stl(PAPatternConfig(num_patterns=5), stl)
    specimens.append((stl, "pressure-advance-pattern.png"))

    # Retraction test towers — 10 levels
    stl = str(tmp / "retraction.stl")
    generate_retraction_tower_stl(RetractionTowerConfig(num_levels=10), stl)
    specimens.append((stl, "retraction-test.png"))

    for stl_path, png_name in specimens:
        png_bytes = gl.render_stl_to_png(stl_path, WIDTH, HEIGHT)
        out = IMAGES_DIR / png_name
        out.write_bytes(png_bytes)
        print(f"  {out}")

    shutil.rmtree(tmp)
    print("Done.")


if __name__ == "__main__":
    main()
