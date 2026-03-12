# CLAUDE.md

## Project Overview

**filament-calibrator** is a CLI tool suite for 3D printer filament calibration.
It contains eleven tools:

- `temperature-tower` — generates, slices, and uploads temperature tower prints
  to find the optimal printing temperature for a filament.
- `extrusion-multiplier` — generates a 40 mm cube, slices it in vase mode
  with classic perimeter generator, and reports the expected wall thickness.
  The user prints the cube, measures the wall with calipers, and calculates
  `EM = expected_width / measured_width`.
- `volumetric-flow` — generates a serpentine vase-mode specimen with
  progressively increasing print speeds to determine maximum volumetric flow
  rate for a filament/hotend combination.
- `pressure-advance` — two methods for finding the optimal PA/Linear Advance
  value:
  - **tower** (default): generates a hollow rectangular tower with sharp
    corners; PA value increases with height.
  - **pattern**: generates nested chevron (V-shape) outlines inside a
    rectangular frame with embossed PA value labels; each chevron is
    printed at a different PA value — inspect which has the sharpest
    corners.  PA insertion is X-based (by chevron tip position).
- `retraction-test` — generates two cylindrical towers spaced apart;
  PrusaSlicer's travel moves between them trigger retraction.  At each
  height level the firmware retraction length is changed via
  `M207 S<length>`, so the user can inspect stringing at each height to
  find the optimal retraction distance.
- `shrinkage-test` — generates a parametric 3-axis cross specimen
  (three perpendicular arms with window cutouts and axis labels),
  slices it with standard settings, and uploads.  The user prints
  the cross, measures each arm with calipers, and calculates
  per-axis shrinkage: `shrinkage % = (nominal − measured) / nominal × 100`.
- `retraction-speed` — reuses the two-tower retraction model but varies
  retraction *speed* instead of length.  Firmware retraction speed is
  changed via `M207 S<length> F<speed>` at each height level while
  keeping retraction length fixed.
- `bridging-test` — generates a row of pillar pairs with flat bridges
  at increasing span lengths.  No G-code insertion; the user inspects
  bridge quality at each span to determine the printer's bridging
  capability.
- `overhang-test` — generates a back wall with angled ramp surfaces
  at increasing overhang angles.  Supports are always disabled so the
  user can evaluate overhang quality at each angle.
- `tolerance-test` — generates a flat plate with circular through-holes
  and matching cylindrical pegs at specified diameters.  The user prints
  the specimen, measures holes and pegs with calipers, and calculates
  dimensional accuracy.
- `cooling-test` — generates a single cylindrical tower; fan speed is
  changed via `M106` at each height level so the user can inspect
  print quality at different cooling rates.

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
  _cq_compat.py    # CadQuery/casadi import compatibility helpers for
                    #   PyInstaller bundles (stub_casadi, ensure_cq)
  slicer.py         # PrusaSlicer CLI wrapper (slice_tower, slice_flow_specimen,
                    #   slice_pa_specimen, slice_pa_pattern, slice_em_specimen,
                    #   slice_retraction_specimen, slice_shrinkage_specimen,
                    #   slice_bridge_specimen, slice_overhang_specimen,
                    #   slice_tolerance_specimen, slice_cooling_specimen)
  tempinsert.py     # G-code temperature command insertion
  em_cli.py         # extrusion-multiplier argparse CLI, pipeline orchestration
  em_model.py       # CadQuery parametric cube model for EM calibration
  flow_cli.py       # volumetric-flow argparse CLI, pipeline orchestration
  flow_model.py     # CadQuery parametric serpentine specimen model
  flow_insert.py    # G-code feedrate override insertion for flow levels;
                    #   _is_extrusion_move and flow_to_feedrate imported from gcode-lib
  pa_cli.py         # pressure-advance argparse CLI, pipeline orchestration
  pa_model.py       # CadQuery parametric hollow rectangular tower model
  pa_pattern.py     # CadQuery parametric chevron pattern model for PA calibration
  pa_insert.py      # G-code pressure advance command insertion
  ini_writer.py     # Merge calibration results into PrusaSlicer .ini configs.
                    #   CalibrationResults dataclass: printer, temperature,
                    #   max_volumetric_speed, pa_value, extrusion_multiplier,
                    #   retraction_length, retraction_speed, xy_shrinkage,
                    #   z_shrinkage.
                    #   Helpers (replace_ini_value, pa_command,
                    #   inject_pa_into_start_gcode) imported from gcode-lib
  retraction_cli.py   # retraction-test argparse CLI, pipeline orchestration
  retraction_model.py # CadQuery parametric two-tower retraction test model
  retraction_insert.py # G-code M207 retraction length command insertion
  shrinkage_cli.py    # shrinkage-test argparse CLI, pipeline orchestration
  shrinkage_model.py  # CadQuery parametric 3-axis cross model for shrinkage
  retraction_speed_insert.py # G-code M207 retraction speed command insertion
  retraction_speed_cli.py    # retraction-speed argparse CLI, pipeline orchestration
  bridge_model.py     # CadQuery parametric pillar-pair bridge test model
  bridge_cli.py       # bridging-test argparse CLI, pipeline orchestration
  overhang_model.py   # CadQuery parametric overhang ramp test model
  overhang_cli.py     # overhang-test argparse CLI, pipeline orchestration
  tolerance_model.py  # CadQuery parametric hole/peg tolerance test model
  tolerance_cli.py    # tolerance-test argparse CLI, pipeline orchestration
  cooling_model.py    # CadQuery parametric cylindrical cooling tower model
  cooling_insert.py   # G-code M106 fan speed command insertion
  cooling_cli.py      # cooling-test argparse CLI, pipeline orchestration
  gui.py            # Streamlit browser GUI wrapping all eleven CLIs.
                    #   Tabs: Temperature Tower, Extrusion Multiplier,
                    #   Retraction (Distance + Speed modes), Pressure Advance,
                    #   Volumetric Flow, Shrinkage & Tolerance, Bridging &
                    #   Overhang, Cooling, Results.
                    #   Calibration results persistence (load_saved_results,
                    #   save_results, results_to_dict,
                    #   apply_saved_results_to_session) to
                    #   ~/.config/filament-calibrator/results.json keyed by
                    #   filament_type|nozzle_size|printer
```

### Key Dependencies

- **cadquery** (>= 2.4): Parametric CAD model generation (OCCT kernel)
- **gcode-lib** (>= 1.1.7): G-code parsing, PrusaSlicer integration,
  PrusaLink API, filament presets, printer G-code templates, thumbnail
  injection, INI parsing/writing helpers, flow/PA helpers. Published on PyPI.
- **vtk** (>= 9.0): Off-screen STL rendering for bgcode thumbnail
  generation. Transitive dependency; optional at runtime (thumbnails
  skipped if absent).
- **streamlit** (>= 1.28): Browser-based GUI. Optional; install via
  `pip install -e ".[gui]"`.
- **tomli** (>= 2.0, Python < 3.11 only): TOML parsing fallback

### Pipeline Flows

**temperature-tower** (`cli.run()`):
load_config → apply_config → resolve_preset → generate_tower_stl →
slice_tower → load G-code → inject_thumbnails → patch_slicer_metadata →
insert_temperatures → save → optional upload.

**volumetric-flow** (`flow_cli.run()`):
load_config → apply_config → validate_flow_args → resolve_preset →
generate_flow_specimen_stl → slice_flow_specimen (vase mode) → load G-code →
inject_thumbnails → patch_slicer_metadata → compute_flow_levels →
insert_flow_rates → save → optional upload.

**pressure-advance — tower** (`pa_cli.run()`):
load_config → apply_config → validate_pa_args → resolve_preset →
generate_pa_tower_stl → slice_pa_specimen → load G-code →
inject_thumbnails → patch_slicer_metadata → compute_pa_levels →
insert_pa_commands → save → optional upload.

**pressure-advance — pattern** (`pa_cli.run()`):
load_config → apply_config → validate_pa_args → resolve_preset →
generate_pa_pattern_stl (chevrons + frame + labels) →
slice_pa_pattern → load G-code → inject_thumbnails →
patch_slicer_metadata → compute_pa_pattern_regions (X-based) →
insert_pa_pattern_commands → save → optional upload.

**extrusion-multiplier** (`em_cli.run()`):
load_config → apply_config → resolve_preset → generate_em_cube_stl →
slice_em_specimen (vase mode, classic walls) → load G-code →
inject_thumbnails → patch_slicer_metadata → save →
print expected wall thickness → optional upload.

**retraction-test** (`retraction_cli.run()`):
load_config → apply_config → validate_retraction_args → resolve_preset →
generate_retraction_tower_stl → slice_retraction_specimen
(firmware retraction) → load G-code → inject_thumbnails →
patch_slicer_metadata → compute_retraction_levels →
insert_retraction_commands (M207) → save → optional upload.

**shrinkage-test** (`shrinkage_cli.run()`):
load_config → apply_config → resolve_preset →
generate_shrinkage_cross_stl → slice_shrinkage_specimen
(standard slicing) → load G-code → inject_thumbnails →
patch_slicer_metadata → save →
print expected dimensions → optional upload.

**retraction-speed** (`retraction_speed_cli.run()`):
load_config → apply_config → validate_retraction_speed_args → resolve_preset →
generate_retraction_tower_stl (reuses retraction_model) →
slice_retraction_specimen (firmware retraction) → load G-code →
inject_thumbnails → patch_slicer_metadata → compute_retraction_speed_levels →
insert_retraction_speed_commands (M207 F) → save → optional upload.

**bridging-test** (`bridge_cli.run()`):
load_config → apply_config → resolve_preset →
generate_bridge_stl (pillar pairs + bridges) →
slice_bridge_specimen → load G-code → inject_thumbnails →
patch_slicer_metadata → save →
print span list → optional upload.

**overhang-test** (`overhang_cli.run()`):
load_config → apply_config → resolve_preset →
generate_overhang_stl (back wall + angled ramps) →
slice_overhang_specimen (supports disabled) → load G-code →
inject_thumbnails → patch_slicer_metadata → save →
print angle list → optional upload.

**tolerance-test** (`tolerance_cli.run()`):
load_config → apply_config → resolve_preset →
generate_tolerance_stl (holes + pegs plate) →
slice_tolerance_specimen → load G-code → inject_thumbnails →
patch_slicer_metadata → save →
print diameter table → optional upload.

**cooling-test** (`cooling_cli.run()`):
load_config → apply_config → validate_cooling_args → resolve_preset →
generate_cooling_tower_stl → slice_cooling_specimen (auto-fan disabled) →
load G-code → inject_thumbnails → patch_slicer_metadata →
compute_cooling_levels → insert_cooling_commands (M106) → save →
optional upload.

### Filament Preset System

All eleven CLIs use `--filament-type` to look up defaults from
`gcode_lib.FILAMENT_PRESETS`.  Known presets (PLA, PETG, ABS, ASA, TPU, etc.)
automatically set nozzle temperature, bed temperature, and fan speed.
Explicit CLI arguments (`--nozzle-temp`, `--bed-temp`, `--fan-speed`)
override the preset.  Unknown filament names fall back to safe defaults
(210°C / 60°C / 100% fan).

### Slicer Configuration

`slicer.py` contains several sets of defaults:

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
- `PA_PATTERN_SLICER_ARGS` — for PA chevron pattern slicing.  Uses the same
  base settings as the tower but with wall count derived from the pattern
  config.  Used by `slice_pa_pattern()`.
- `EM_SLICER_ARGS` — for extrusion multiplier cube slicing (1 perimeter,
  no infill, 5mm brim).  `slice_em_specimen()` always forces
  `--spiral-vase`, `--perimeter-generator=classic`, and
  `--support-material=0`.
- `RETRACTION_SLICER_ARGS` — for retraction test tower slicing
  (2 perimeters, 15% infill).  `slice_retraction_specimen()` always
  forces `--use-firmware-retraction` and `--wipe=0` so PrusaSlicer
  emits G10/G11 instead of explicit retract moves, allowing M207
  commands to control the retraction length.  Wipe must be disabled
  because PrusaSlicer considers it incompatible with firmware
  retraction.
- `SHRINKAGE_SLICER_ARGS` — for shrinkage cross slicing (3 perimeters,
  20% infill, 5 top / 4 bottom solid layers).  Standard slicing for
  dimensional accuracy — no vase mode, no firmware retraction.
- `BRIDGE_SLICER_ARGS` — for bridging test slicing (2 perimeters,
  15% infill).  Standard slicing for bridge quality evaluation.
- `OVERHANG_SLICER_ARGS` — for overhang test slicing (2 perimeters,
  15% infill).  `slice_overhang_specimen()` always forces
  `--support-material=0` so overhang quality can be evaluated
  without support structures.
- `TOLERANCE_SLICER_ARGS` — for tolerance test slicing (3 perimeters,
  20% infill, 5 top / 4 bottom solid layers).  Same settings as
  `SHRINKAGE_SLICER_ARGS` for dimensional accuracy.
- `COOLING_SLICER_ARGS` — for cooling test slicing (2 perimeters,
  15% infill).  `slice_cooling_specimen()` always forces
  `--cooling=0` to disable PrusaSlicer's automatic fan management
  so that M106 G-code commands control fan speed directly.

All slicer functions accept `nozzle_diameter` to pass `--nozzle-diameter` to
PrusaSlicer, and pass `--center` and `--bed-shape` for Prusa MK-series bed
geometry (250×220mm).  All default to `binary_gcode=True` which passes
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
- Shared CLI helpers (`_apply_config`, `_resolve_output_dir`, `_UNSET`,
  `_KNOWN_TYPES`, `_ARGPARSE_DEFAULTS`) live in `cli.py` and are imported
  by `em_cli.py`, `flow_cli.py`, `pa_cli.py`, `retraction_cli.py`,
  `shrinkage_cli.py`, `retraction_speed_cli.py`, `bridge_cli.py`,
  `overhang_cli.py`, `tolerance_cli.py`, and `cooling_cli.py`.
  Generic filename/preset
  helpers (`unique_suffix`, `safe_filename_part`, `gcode_ext`,
  `resolve_filament_preset`) are imported from `gcode_lib`.

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
pip install -e ".[gui]"             # with Streamlit GUI
```

Entry points:

- `temperature-tower` → `filament_calibrator.cli:main`
- `extrusion-multiplier` → `filament_calibrator.em_cli:main`
- `volumetric-flow` → `filament_calibrator.flow_cli:main`
- `pressure-advance` → `filament_calibrator.pa_cli:main`
- `retraction-test` → `filament_calibrator.retraction_cli:main`
- `shrinkage-test` → `filament_calibrator.shrinkage_cli:main`
- `retraction-speed` → `filament_calibrator.retraction_speed_cli:main`
- `bridging-test` → `filament_calibrator.bridge_cli:main`
- `overhang-test` → `filament_calibrator.overhang_cli:main`
- `tolerance-test` → `filament_calibrator.tolerance_cli:main`
- `cooling-test` → `filament_calibrator.cooling_cli:main`
- `filament-calibrator-gui` → `filament_calibrator.gui:main` (requires `[gui]` extra)

## Common Tasks

- **Add a new filament preset**: Add to `FILAMENT_PRESETS` in
  `gcode-lib/gcode_lib.py`. Required keys: hotend, bed, fan, retract,
  temp_min, temp_max, speed, enclosure.
- **Change tower geometry**: Edit constants in `model.py` (BASE_*, TIER_*).
- **Change flow specimen geometry**: Edit constants in `flow_model.py`
  (SPECIMEN_WIDTH, ARM_THICKNESS, GAP_WIDTH, NUM_ARMS, LEVEL_HEIGHT).
- **Change PA tower geometry**: Edit constants in `pa_model.py`
  (TOWER_WIDTH, TOWER_DEPTH, WALL_THICKNESS, LEVEL_HEIGHT).
- **Change PA pattern geometry**: Edit constants in `pa_pattern.py`
  (DEFAULT_CORNER_ANGLE, DEFAULT_ARM_LENGTH, DEFAULT_WALL_THICKNESS,
  DEFAULT_PATTERN_SPACING, DEFAULT_FRAME_OFFSET, DEFAULT_LABEL_HEIGHT).
- **Change EM cube geometry**: Edit `CUBE_SIZE` in `em_model.py`.
- **Change retraction tower geometry**: Edit constants in
  `retraction_model.py` (TOWER_DIAMETER, TOWER_SPACING, BASE_LENGTH,
  BASE_WIDTH, BASE_HEIGHT, LEVEL_HEIGHT).
- **Change shrinkage cross geometry**: Edit constants in
  `shrinkage_model.py` (ARM_LENGTH, ARM_SIZE, WINDOW_SIZE,
  WINDOW_INTERVAL, LABEL_DEPTH, LABEL_FONT_SIZE).
- **Change bridge test geometry**: Edit constants in `bridge_model.py`
  (DEFAULT_SPANS, PILLAR_WIDTH, PILLAR_DEPTH, PILLAR_HEIGHT,
  BRIDGE_THICKNESS, BASE_HEIGHT, BASE_MARGIN).
- **Change overhang test geometry**: Edit constants in `overhang_model.py`
  (DEFAULT_ANGLES, WALL_HEIGHT, WALL_THICKNESS, SURFACE_LENGTH,
  SURFACE_WIDTH, SURFACE_THICKNESS, SURFACE_SPACING, BASE_HEIGHT,
  BASE_MARGIN).
- **Change tolerance test geometry**: Edit constants in `tolerance_model.py`
  (DEFAULT_DIAMETERS, PLATE_THICKNESS, PEG_HEIGHT, PEG_BASE_HEIGHT,
  COLUMN_SPACING, ROW_SPACING, PLATE_MARGIN, BASE_HEIGHT).
- **Change cooling tower geometry**: Edit constants in `cooling_model.py`
  (TOWER_DIAMETER, BASE_LENGTH, BASE_WIDTH, BASE_HEIGHT, LEVEL_HEIGHT).
- **Change slicer defaults**: Edit `DEFAULT_SLICER_ARGS` (temp tower),
  `VASE_MODE_SLICER_ARGS` (flow specimen), `PA_SLICER_ARGS` (PA tower),
  `EM_SLICER_ARGS` (EM cube), `RETRACTION_SLICER_ARGS` (retraction
  towers), `SHRINKAGE_SLICER_ARGS` (shrinkage cross),
  `BRIDGE_SLICER_ARGS` (bridging), `OVERHANG_SLICER_ARGS` (overhang),
  `TOLERANCE_SLICER_ARGS` (tolerance), or `COOLING_SLICER_ARGS`
  (cooling) in `slicer.py`.
- **Add a new calibration tool**: Create a new module + CLI entry point in
  `pyproject.toml [project.scripts]`.  Import shared helpers from `cli.py`.
- **Add a new config key**: Add to `CONFIG_KEYS` in `config.py`, add
  corresponding entry in `_ARGPARSE_DEFAULTS` in `cli.py`.
- **Access persisted calibration results**: Results for each
  (filament, nozzle, printer) combination are auto-saved to
  `~/.config/filament-calibrator/results.json` and restored when
  switching combinations in the GUI sidebar.  Key format:
  `"FILAMENT|nozzle_size|PRINTER"`.  Use `load_saved_results()` /
  `save_results()` for programmatic access.
