# CLAUDE.md

## Project Overview

**filament-calibrator** is a CLI tool suite for 3D printer filament calibration.
It contains three tools:

- `temperature-tower` — generates, slices, and uploads temperature tower prints
  to find the optimal printing temperature for a filament.
- `volumetric-flow` — generates a serpentine vase-mode specimen with
  progressively increasing print speeds to determine maximum volumetric flow
  rate for a filament/hotend combination.
- `pressure-advance` — generates a hollow rectangular tower with sharp corners,
  slices it, and inserts pressure advance commands at each height level to find
  the optimal PA/Linear Advance value.

## Architecture

```
src/filament_calibrator/
  __init__.py       # Package init, __version__
  __main__.py       # python -m filament_calibrator support
  cli.py            # temperature-tower argparse CLI, pipeline orchestration,
                    #   shared helpers (_UNSET, _KNOWN_TYPES, _ARGPARSE_DEFAULTS,
                    #   _apply_config, _resolve_output_dir)
  config.py         # TOML config file loading
  model.py          # CadQuery parametric temperature tower model
  slicer.py         # PrusaSlicer CLI wrapper (slice_tower, slice_flow_specimen,
                    #   slice_pa_specimen)
  tempinsert.py     # G-code temperature command insertion
  flow_cli.py       # volumetric-flow argparse CLI, pipeline orchestration
  flow_model.py     # CadQuery parametric serpentine specimen model
  flow_insert.py    # G-code feedrate override insertion for flow levels
  pa_cli.py         # pressure-advance argparse CLI, pipeline orchestration
  pa_model.py       # CadQuery parametric hollow rectangular tower model
  pa_insert.py      # G-code pressure advance command insertion
  printer_gcode.py  # Printer-specific start/end G-code templates and rendering
  thumbnail.py      # STL → PNG rendering (VTK) and bgcode thumbnail injection
```

### Key Dependencies

- **cadquery** (>= 2.4): Parametric CAD model generation (OCCT kernel)
- **gcode-lib** (>= 1.0.0): G-code parsing, PrusaSlicer integration,
  PrusaLink API, filament presets. Published on PyPI.
- **vtk** (>= 9.0): Off-screen STL rendering for bgcode thumbnail
  generation. Transitive dependency; optional at runtime (thumbnails
  skipped if absent).
- **tomli** (>= 2.0, Python < 3.11 only): TOML parsing fallback

### Pipeline Flows

**temperature-tower** (`cli.run()`):
load_config → apply_config → resolve_preset → generate_tower_stl →
slice_tower → load G-code → inject_thumbnails → insert_temperatures →
save → optional upload.

**volumetric-flow** (`flow_cli.run()`):
load_config → apply_config → validate_flow_args → resolve_preset →
generate_flow_specimen_stl → slice_flow_specimen (vase mode) → load G-code →
inject_thumbnails → compute_flow_levels → insert_flow_rates → save →
optional upload.

**pressure-advance** (`pa_cli.run()`):
load_config → apply_config → validate_pa_args → resolve_preset →
generate_pa_tower_stl → slice_pa_specimen → load G-code →
inject_thumbnails → compute_pa_levels → insert_pa_commands → save →
optional upload.

### Filament Preset System

All three CLIs use `--filament-type` to look up defaults from
`gcode_lib.FILAMENT_PRESETS`.  Known presets (PLA, PETG, ABS, ASA, TPU, etc.)
automatically set nozzle temperature, bed temperature, and fan speed.
Explicit CLI arguments (`--nozzle-temp`, `--bed-temp`, `--fan-speed`)
override the preset.  Unknown filament names fall back to safe defaults
(210°C / 60°C / 100% fan).

### Slicer Configuration

`slicer.py` contains three sets of defaults:

- `DEFAULT_SLICER_ARGS` — for temperature tower slicing (2 perimeters,
  15% infill).  Layer height and extrusion width are derived from
  `--nozzle-size` (default 0.4mm → 0.2mm layers, 0.45mm extrusion width).
- `VASE_MODE_SLICER_ARGS` — for flow specimen slicing (1 perimeter, no infill,
  5mm brim, spiral-vase mode).  `layer-height` and `extrusion-width` are
  passed explicitly by `slice_flow_specimen()`, derived from `--nozzle-size`
  unless the user provides explicit values.
- `PA_SLICER_ARGS` — for PA calibration tower slicing (2 perimeters, 0% infill,
  0 top/bottom solid layers).  `layer-height` and `extrusion-width` are passed
  explicitly by `slice_pa_specimen()`, derived from `--nozzle-size`.

All three functions accept `nozzle_diameter` to pass `--nozzle-diameter` to
PrusaSlicer, and pass `--center` and `--bed-shape` for Prusa MK-series bed
geometry (250×210mm).  All three default to `binary_gcode=True` which passes
`--binary-gcode` to PrusaSlicer, producing `.bgcode` output with embedded
thumbnail previews.  Use `--ascii-gcode` on the CLI to switch to text
`.gcode` output.

**Nozzle-size derivation formulas** (matching PrusaSlicer auto-width):
- `layer_height = nozzle_size × 0.5` → 0.4→0.2, 0.6→0.3, 0.8→0.4
- `extrusion_width = nozzle_size × 1.125` → 0.4→0.45, 0.6→0.68, 0.8→0.9

## Code Conventions

- Python 3.10+, `from __future__ import annotations` in every module
- Type hints on all function signatures
- Immutable transforms (return new data, don't mutate inputs) following
  gcode-lib patterns
- `_UNSET = object()` sentinel for distinguishing "user didn't set" from None
  in argparse
- Filament preset lookup is case-insensitive (`.upper()`)
- Shared CLI helpers (`_apply_config`, `_resolve_output_dir`, `_gcode_ext`,
  `_UNSET`, `_KNOWN_TYPES`, `_ARGPARSE_DEFAULTS`) live in `cli.py` and are
  imported by `flow_cli.py` and `pa_cli.py`

## Testing

```bash
pytest tests/ --cov=src/filament_calibrator --cov-report=term-missing --cov-fail-under=100
```

- 100% statement coverage is required and enforced
- CadQuery is mocked in model tests (geometry ops verified via call assertions)
- PrusaSlicer and PrusaLink are mocked in slicer/CLI tests
- G-code insertion tests use synthetic inline G-code strings
- Tests use `unittest.mock.patch` for external dependencies

## Build & Install

```bash
pip install -e .                    # editable install
```

Entry points:

- `temperature-tower` → `filament_calibrator.cli:main`
- `volumetric-flow` → `filament_calibrator.flow_cli:main`
- `pressure-advance` → `filament_calibrator.pa_cli:main`

## Common Tasks

- **Add a new filament preset**: Add to `FILAMENT_PRESETS` in
  `gcode-lib/gcode_lib.py`. Required keys: hotend, bed, fan, retract,
  temp_min, temp_max, speed, enclosure.
- **Change tower geometry**: Edit constants in `model.py` (BASE_*, TIER_*).
- **Change flow specimen geometry**: Edit constants in `flow_model.py`
  (SPECIMEN_WIDTH, ARM_THICKNESS, GAP_WIDTH, NUM_ARMS, LEVEL_HEIGHT).
- **Change PA tower geometry**: Edit constants in `pa_model.py`
  (TOWER_WIDTH, TOWER_DEPTH, WALL_THICKNESS, LEVEL_HEIGHT).
- **Change slicer defaults**: Edit `DEFAULT_SLICER_ARGS` (temp tower),
  `VASE_MODE_SLICER_ARGS` (flow specimen), or `PA_SLICER_ARGS` (PA tower)
  in `slicer.py`.
- **Add a new calibration tool**: Create a new module + CLI entry point in
  `pyproject.toml [project.scripts]`.  Import shared helpers from `cli.py`.
- **Add a new config key**: Add to `CONFIG_KEYS` in `config.py`, add
  corresponding entry in `_ARGPARSE_DEFAULTS` in `cli.py`.
