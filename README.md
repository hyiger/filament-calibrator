# filament-calibrator

CLI tool suite for 3D printer filament calibration on Prusa printers.

**Four calibration tools included:**

- **`temperature-tower`** — generates a parametric temperature tower, slices it
  with PrusaSlicer, injects per-tier temperature changes into the G-code, and
  optionally uploads the result to your printer via PrusaLink.
- **`extrusion-multiplier`** — generates a 40 mm cube, slices it in vase mode
  with classic perimeter generator, and reports the expected wall thickness.
  Print the cube, measure the wall with calipers, and calculate
  `EM = expected_width / measured_width`.
- **`volumetric-flow`** — generates a serpentine wall specimen, slices it in
  spiral vase mode, and injects progressively increasing print speeds to
  determine the maximum volumetric flow rate for a filament/hotend combination.
- **`pressure-advance`** — two methods for finding the optimal PA/Linear
  Advance value: **tower** (default) generates a hollow tower with sharp
  corners where PA varies by height; **pattern** generates nested chevron
  outlines where PA varies by X position.

## Prerequisites

- **Python 3.10 or 3.12** (see [note on Python versions](#python-version-compatibility)
  below)
- **PrusaSlicer** installed and available on your `PATH` (or provide
  `--prusaslicer-path`). Download from
  [prusa3d.com](https://www.prusa3d.com/page/prusaslicer_424/).
- A Prusa printer with **PrusaLink** enabled (only needed for uploading).

## Installation

Create a virtual environment and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This pulls all Python dependencies from PyPI automatically:
[CadQuery](https://cadquery.readthedocs.io/) for model generation and
[gcode-lib](https://github.com/hyiger/gcode-lib) (>= 1.0.0) for G-code
manipulation.

The `temperature-tower`, `extrusion-multiplier`, `volumetric-flow`, and
`pressure-advance` commands are available whenever the venv is active. To
reactivate later, run `source .venv/bin/activate` from the project directory.

### Python version compatibility

CadQuery depends on [cadquery-ocp](https://pypi.org/project/cadquery-ocp/),
which ships pre-built binary wheels for specific Python versions. Wheels are
available for **Python 3.10 and 3.12** on all major platforms (Linux x86-64,
macOS x86-64 / ARM64, Windows x86-64). Other Python versions (3.11, 3.13,
3.14) have limited or no wheel coverage.

If `pip install` fails with a dependency resolution error mentioning
`cadquery-ocp`, create a venv with a supported Python version:

```bash
# macOS with Homebrew
brew install python@3.12
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Conda alternative

If pip installation doesn't work for your platform, CadQuery can be installed
via conda-forge:

```bash
conda create -n filament-cal python=3.12
conda activate filament-cal
mamba install -c conda-forge cadquery
pip install -e .
```

> **Note:** Install conda packages first, then pip packages. See the
> [Anaconda docs](https://www.anaconda.com/blog/using-pip-in-a-conda-environment)
> for details on mixing conda and pip.

## Filament Presets

All four tools use presets from `gcode-lib` to set smart defaults for each filament
type. Known presets: **ABS**, **ASA**, **HIPS**, **PA**, **PA-CF**, **PC**,
**PCTG**, **PETG**, **PETG-CF**, **PLA**, **PLA-CF**, **PP**, **PPA**, **TPU**.

Each preset provides: recommended hotend temperature, bed temperature, fan
speed, retraction distance, safe temperature range (`temp_min`/`temp_max`),
print speed, and enclosure recommendation.

When you specify `--filament-type` (default `PLA`), the tool uses the preset
to set default temperatures and fan speed. All preset values can be overridden
with explicit CLI flags.

## Configuration

Save commonly reused settings in a TOML file so you don't have to pass them
on every run. To get started, copy the example file:

```bash
cp filament-calibrator.example.toml filament-calibrator.toml
```

Then edit it with your printer and slicer details:

```toml
# Printer connection (required for uploading)
printer-url = "http://192.168.1.100"
api-key = "your-prusalink-api-key"

# Printer model — generates printer-specific start/end G-code
# for pressure-advance (when no --config-ini is given).
# Supported: coreone, coreonel, mk4s, mini, xl
# printer = "coreone"

# Slicer setup (prusaslicer-path is only needed if PrusaSlicer is not
# installed in a standard location — the tool auto-detects it on PATH)
# prusaslicer-path = "/usr/bin/prusa-slicer"
# config-ini = "/path/to/printer-profile.ini"

# Bed centre in mm — default is 125,110 (Prusa MK-series 250×220 mm bed).
# Auto-set by printer if specified. For Prusa MINI, use 90,90.
# bed-center = "125,110"

# Nozzle size in mm — derives layer height (nozzle × 0.5) and
# extrusion width (nozzle × 1.125). Default: 0.4
# nozzle-size = 0.4

# Defaults
filament-type = "PLA"
output-dir = "./output"
```

All keys are optional — include only what you need. In particular,
`prusaslicer-path` can be omitted if PrusaSlicer is installed in a standard
location (e.g. `/usr/bin/prusa-slicer`, `/Applications/PrusaSlicer.app`, or
anywhere on your `PATH`).

The config file is shared between all four tools.

### Config file locations

The tools look for a config file in this order (first found wins):

| Priority | Location | Use case |
|----------|----------|----------|
| 1 | `--config <path>` | Explicit override |
| 2 | `./filament-calibrator.toml` | Per-project settings |
| 3 | `~/.config/filament-calibrator/config.toml` | User-wide defaults |

CLI arguments always override config file values, so you can set your usual
defaults in the file and override individual flags as needed.

---

## Temperature Tower

### Quick Start

Generate and upload a PLA temperature tower with preset defaults:

```bash
temperature-tower \
  --printer-url http://192.168.1.100 \
  --api-key YOUR_API_KEY
```

Generate without uploading:

```bash
temperature-tower --no-upload --output-dir ./output --keep-files
```

### How It Works

1. **Model generation** — CadQuery builds a parametric temp tower STL matching
   the classic OpenSCAD design: filleted base, stacked tiers with overhang
   tests (45/35 deg), bridge holes, cones, and engraved temperature labels.

2. **Slicing** — PrusaSlicer CLI slices the STL using either a user-supplied
   `.ini` profile or built-in defaults (layer height and extrusion width
   derived from `--nozzle-size`, 2 perimeters, 15% infill, no supports).

3. **Temperature insertion** — `M104` commands are inserted at the G-code
   layer boundaries corresponding to each tier, so the printer changes
   temperature as it moves up the tower.

4. **Upload** — The final G-code is uploaded to the printer via PrusaLink
   REST API, with optional auto-start.

### CLI Reference

#### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type (preset name or custom) |
| `--start-temp` | from preset `temp_max` | Highest temperature (bottom tier) |
| `--end-temp` | from preset `temp_min` | Lowest temperature (top tier) |
| `--temp-step` | `5` | Temperature decrease per tier (deg C) |
| `--brand-top` | | Optional brand label on top |
| `--brand-bottom` | | Optional brand label on bottom |

Tier count is computed automatically: `(start_temp - end_temp) / temp_step + 1`,
validated to a maximum of 10. Temperatures must be within 150--350 deg C,
`--start-temp` must be at least `--end-temp + --temp-step`, and the range
must be evenly divisible by `--temp-step`.

#### Nozzle Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-size` | `0.4` | Nozzle diameter in mm — derives layer height (`nozzle × 0.5`) and extrusion width (`nozzle × 1.125`) |

#### Slicer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--bed-temp` | from preset | Bed temperature (deg C) |
| `--fan-speed` | from preset | Fan speed (0--100%) |
| `--config-ini` | | PrusaSlicer `.ini` config file |
| `--prusaslicer-path` | auto-detect | Path to PrusaSlicer executable |
| `--printer` | `COREONE` | Printer model — auto-sets bed center/shape, generates start/end G-code, and embeds printer metadata in bgcode |
| `--bed-center` | from `--printer` | Bed centre as X,Y in mm (auto-set by `--printer`) |
| `--extra-slicer-args` | | Additional PrusaSlicer CLI args (must be last) |

Supported printers for `--printer`: **COREONE**, **COREONEL**, **MK4S**
(alias: MK4), **MINI**, **XL**.

#### Printer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--printer-url` | | PrusaLink URL (e.g. `http://192.168.1.100`) |
| `--api-key` | | PrusaLink API key |
| `--no-upload` | `false` | Skip uploading to printer |
| `--print-after-upload` | `false` | Start printing after upload |

#### Output Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | temp dir | Directory for output files |
| `--keep-files` | `false` | Keep intermediate STL and raw G-code |
| `--ascii-gcode` | `false` | Output ASCII `.gcode` instead of binary `.bgcode` |
| `--config` | auto-detect | Path to a TOML config file |
| `-v`, `--verbose` | `false` | Show detailed debug output |

### Examples

PETG tower with 5-degree steps:

```bash
temperature-tower --filament-type PETG --temp-step 5 --no-upload
```

Custom range for ABS:

```bash
temperature-tower \
  --filament-type ABS \
  --start-temp 270 \
  --end-temp 240 \
  --temp-step 5 \
  --bed-temp 110 \
  --no-upload \
  --output-dir ./abs-tower
```

With a 0.6mm nozzle (auto-sets 0.3mm layer height, 0.68mm extrusion width):

```bash
temperature-tower --nozzle-size 0.6 --no-upload
```

Use a PrusaSlicer profile:

```bash
temperature-tower \
  --config-ini ~/PrusaSlicer/my_profile.ini \
  --no-upload
```

---

## Extrusion Multiplier

### Quick Start

Generate a PLA extrusion multiplier cube with default settings:

```bash
extrusion-multiplier --no-upload --output-dir ./output --keep-files
```

Upload directly to printer:

```bash
extrusion-multiplier \
  --printer-url http://192.168.1.100 \
  --api-key YOUR_API_KEY
```

### How It Works

1. **Model generation** — CadQuery builds a simple 40 mm cube (configurable
   with `--cube-size`).

2. **Slicing** — PrusaSlicer slices in `--spiral-vase` mode with
   `--perimeter-generator=classic` (required for accurate single-wall width),
   a 5 mm brim, and no supports.

3. **Expected width** — The tool prints the expected wall thickness (equal to
   the extrusion width, default 0.45 mm for a 0.4 mm nozzle).

4. **Upload** — Same PrusaLink upload path as the other tools.

### Interpreting the Print

Print the cube, then measure the wall thickness at several points with digital
calipers. Calculate: **EM = expected_width / measured_width**. For example, if
the expected width is 0.45 mm and you measure 0.47 mm, set
`EM = 0.45 / 0.47 = 0.957`. Apply this value in PrusaSlicer under
Filament Settings → Filament → Extrusion multiplier.

### CLI Reference

#### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type (preset name or custom) |
| `--cube-size` | `40.0` | Cube size in mm |

#### Nozzle Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-size` | `0.4` | Nozzle diameter in mm — derives layer height (`nozzle × 0.5`) and extrusion width (`nozzle × 1.125`) |

#### Slicer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-temp` | from preset | Nozzle temperature (deg C) — overrides preset |
| `--bed-temp` | from preset | Bed temperature (deg C) — overrides preset |
| `--fan-speed` | from preset | Fan speed (0--100%) — overrides preset |
| `--layer-height` | from `--nozzle-size` | Slicer layer height in mm (default: nozzle × 0.5) |
| `--extrusion-width` | from `--nozzle-size` | Slicer extrusion width in mm (default: nozzle × 1.125) |
| `--config-ini` | | PrusaSlicer `.ini` config file |
| `--prusaslicer-path` | auto-detect | Path to PrusaSlicer executable |
| `--printer` | `COREONE` | Printer model — auto-sets bed center/shape and embeds printer metadata in bgcode |
| `--bed-center` | from `--printer` | Bed centre as X,Y in mm (auto-set by `--printer`) |
| `--extra-slicer-args` | | Additional PrusaSlicer CLI args (must be last) |

Supported printers for `--printer`: **COREONE**, **COREONEL**, **MK4S**
(alias: MK4), **MINI**, **XL**.

#### Printer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--printer-url` | | PrusaLink URL (e.g. `http://192.168.1.100`) |
| `--api-key` | | PrusaLink API key |
| `--no-upload` | `false` | Skip uploading to printer |
| `--print-after-upload` | `false` | Start printing after upload |

#### Output Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | temp dir | Directory for output files |
| `--keep-files` | `false` | Keep intermediate STL and raw G-code |
| `--ascii-gcode` | `false` | Output ASCII `.gcode` instead of binary `.bgcode` |
| `--config` | auto-detect | Path to a TOML config file |
| `-v`, `--verbose` | `false` | Show detailed debug output |

### Examples

PETG with custom temperature:

```bash
extrusion-multiplier --filament-type PETG --nozzle-temp 240 --no-upload
```

With a 0.6mm nozzle (auto-sets 0.3mm layer height, 0.68mm extrusion width):

```bash
extrusion-multiplier --nozzle-size 0.6 --no-upload
```

Custom cube size:

```bash
extrusion-multiplier --cube-size 30 --no-upload
```

---

## Volumetric Flow

### Quick Start

Test PLA flow from 5 to 20 mm³/s in 1 mm³/s steps:

```bash
volumetric-flow \
  --start-speed 5 --end-speed 20 --step 1 \
  --no-upload --output-dir ./output --keep-files
```

Upload directly to printer:

```bash
volumetric-flow \
  --start-speed 5 --end-speed 20 --step 1 \
  --printer-url http://192.168.1.100 \
  --api-key YOUR_API_KEY
```

### How It Works

1. **Model generation** — CadQuery builds a serpentine (E-shaped) wall: three
   horizontal arms connected by a spine, with rounded ends. This creates a
   long continuous outer perimeter ideal for sustained extrusion testing in
   vase mode. The model height equals `num_levels * level_height`.

2. **Slicing** — PrusaSlicer slices in `--spiral-vase` mode (single wall,
   continuous Z rise) with a 5mm brim for adhesion.

3. **Feedrate insertion** — The G-code is walked line-by-line tracking Z
   height. At each level boundary, the feedrate on extrusion moves is
   overridden to achieve the target volumetric flow rate using the formula:
   `F = (flow_mm³/s / (layer_height * extrusion_width)) * 60`.

4. **Upload** — Same PrusaLink upload path as the temperature tower.

### Interpreting the Print

Print the specimen and observe where quality degrades — under-extrusion,
layer splitting, or extruder clicking indicate you have exceeded the maximum
flow rate. The last level that printed cleanly is your safe maximum volumetric
flow for that filament/hotend combination.

### CLI Reference

#### Flow Options

| Flag | Default | Description |
|------|---------|-------------|
| `--start-speed` | *required* | Starting volumetric flow rate (mm³/s) |
| `--end-speed` | *required* | Ending volumetric flow rate (mm³/s) |
| `--step` | *required* | Flow rate increment per level (mm³/s) |

The flow range must be evenly divisible by `--step`, and the resulting number
of levels cannot exceed 50.

#### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type — sets nozzle temp, bed temp, and fan speed from preset |
| `--level-height` | `1.0` | Height per flow level in mm |

#### Nozzle Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-size` | `0.4` | Nozzle diameter in mm — derives layer height and extrusion width (see below) |

#### Slicer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-temp` | from preset | Nozzle temperature (deg C) — overrides preset |
| `--bed-temp` | from preset | Bed temperature (deg C) — overrides preset |
| `--fan-speed` | from preset | Fan speed (0--100%) — overrides preset |
| `--layer-height` | from `--nozzle-size` | Slicer layer height in mm (default: nozzle × 0.5) |
| `--extrusion-width` | from `--nozzle-size` | Slicer extrusion width in mm (default: nozzle × 1.125) |
| `--config-ini` | | PrusaSlicer `.ini` config file |
| `--prusaslicer-path` | auto-detect | Path to PrusaSlicer executable |
| `--printer` | `COREONE` | Printer model — auto-sets bed center/shape and embeds printer metadata in bgcode |
| `--bed-center` | from `--printer` | Bed centre as X,Y in mm (auto-set by `--printer`) |
| `--extra-slicer-args` | | Additional PrusaSlicer CLI args (must be last) |

Supported printers for `--printer`: **COREONE**, **COREONEL**, **MK4S**
(alias: MK4), **MINI**, **XL**.

#### Printer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--printer-url` | | PrusaLink URL (e.g. `http://192.168.1.100`) |
| `--api-key` | | PrusaLink API key |
| `--no-upload` | `false` | Skip uploading to printer |
| `--print-after-upload` | `false` | Start printing after upload |

#### Output Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | temp dir | Directory for output files |
| `--keep-files` | `false` | Keep intermediate STL and raw G-code |
| `--ascii-gcode` | `false` | Output ASCII `.gcode` instead of binary `.bgcode` |
| `--config` | auto-detect | Path to a TOML config file |
| `-v`, `--verbose` | `false` | Show detailed debug output |

### Examples

PLA flow test with fine steps:

```bash
volumetric-flow \
  --start-speed 5 --end-speed 15 --step 0.5 \
  --no-upload --output-dir ./output
```

PETG flow test with custom temperatures:

```bash
volumetric-flow \
  --filament-type PETG \
  --start-speed 3 --end-speed 12 --step 1 \
  --nozzle-temp 240 --bed-temp 80 \
  --no-upload
```

With a 0.6mm nozzle (auto-sets 0.3mm layer height, 0.68mm extrusion width):

```bash
volumetric-flow \
  --start-speed 5 --end-speed 20 --step 1 \
  --nozzle-size 0.6 \
  --no-upload
```

Use a PrusaSlicer profile:

```bash
volumetric-flow \
  --start-speed 5 --end-speed 20 --step 1 \
  --config-ini ~/PrusaSlicer/my_profile.ini \
  --no-upload
```

---

## Pressure Advance

### Quick Start

Test PA from 0.0 to 0.10 in 0.01 steps (direct drive extruder):

```bash
pressure-advance \
  --start-pa 0 --end-pa 0.10 --pa-step 0.01 \
  --no-upload --output-dir ./output --keep-files
```

Upload directly to printer:

```bash
pressure-advance \
  --start-pa 0 --end-pa 0.10 --pa-step 0.01 \
  --printer-url http://192.168.1.100 \
  --api-key YOUR_API_KEY
```

### How It Works

Two calibration methods are available via `--method`:

#### Tower method (default)

1. **Model generation** — CadQuery builds a hollow rectangular tower (60×60 mm,
   1.6 mm wall thickness) with perfectly sharp 90° corners. The tower height
   equals `num_levels × level_height`. Sharp corners are critical — they reveal
   PA tuning quality at each level.

2. **Slicing** — PrusaSlicer CLI slices the STL using either a user-supplied
   `.ini` profile or built-in defaults (2 perimeters, 0% infill, no top/bottom
   solid layers). Layer height and extrusion width are derived from
   `--nozzle-size`.

3. **PA command insertion** — Pressure advance (`M900 K<value>`) commands are
   inserted at the G-code layer boundaries corresponding to each level.

#### Pattern method

1. **Model generation** — CadQuery builds nested chevron (V-shape) outlines
   inside a rectangular frame, with embossed PA value labels. Each chevron is
   printed at a different PA value.

2. **Slicing** — PrusaSlicer slices with the wall count matching the pattern
   config (default 3 walls).

3. **PA command insertion** — PA commands are inserted based on X position
   (by chevron tip location) rather than Z height.

### Interpreting the Print

**Tower:** Examine the corners at each level. The level with the sharpest
corners (no bulging, no rounding) is your optimal PA value. The tool prints a
lookup table mapping Z heights to PA values.

**Pattern:** Inspect which chevron has the sharpest corners. The PA value
is embossed next to each chevron for easy identification.

### CLI Reference

#### Pressure Advance Options

| Flag | Default | Description |
|------|---------|-------------|
| `--start-pa` | *required* | Starting PA value (bottom level / first chevron) |
| `--end-pa` | *required* | Ending PA value (top level / last chevron) |
| `--pa-step` | *required* | PA value increment per level |
| `--method` | `tower` | Calibration method: `tower` or `pattern` |

The PA range must be evenly divisible by `--pa-step`, and the resulting number
of levels cannot exceed 50. `--start-pa` must be non-negative.

#### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type — sets nozzle temp, bed temp, and fan speed from preset |
| `--level-height` | `1.0` | Height per PA level in mm (tower method only) |

#### Pattern Method Options

These flags apply only when `--method pattern` is used:

| Flag | Default | Description |
|------|---------|-------------|
| `--corner-angle` | `90` | Full angle at the chevron tip in degrees |
| `--arm-length` | `25.0` | Length of each chevron arm in mm |
| `--wall-count` | `3` | Number of concentric perimeter walls |
| `--num-layers` | `3` | Number of layers (height = num_layers × layer_height) |
| `--pattern-spacing` | `2.0` | Spacing between chevron centres in mm |
| `--frame-offset` | `3.0` | Distance from outermost chevron to frame edge in mm |

#### Nozzle Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-size` | `0.4` | Nozzle diameter in mm — derives layer height and extrusion width |

#### Slicer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-temp` | from preset | Nozzle temperature (deg C) — overrides preset |
| `--bed-temp` | from preset | Bed temperature (deg C) — overrides preset |
| `--fan-speed` | from preset | Fan speed (0--100%) — overrides preset |
| `--layer-height` | from `--nozzle-size` | Slicer layer height in mm (default: nozzle × 0.5) |
| `--extrusion-width` | from `--nozzle-size` | Slicer extrusion width in mm (default: nozzle × 1.125) |
| `--config-ini` | | PrusaSlicer `.ini` config file |
| `--prusaslicer-path` | auto-detect | Path to PrusaSlicer executable |
| `--printer` | `COREONE` | Printer model — generates start/end G-code, auto-sets bed center/shape, and embeds printer metadata in bgcode (see below) |
| `--bed-center` | from `--printer` | Bed centre as X,Y in mm (auto-set by `--printer`) |
| `--extra-slicer-args` | | Additional PrusaSlicer CLI args (must be last) |

#### Printer-Specific Start/End G-code

When `--printer` is specified and no `--config-ini` is given, the tool
renders printer-specific start and end G-code and passes it to PrusaSlicer.
This eliminates the need for a separate slicer profile and produces ready-to-
print output with proper homing, mesh bed leveling, and parking sequences.

Supported printers: **COREONE**, **COREONEL**, **MK4S** (alias: MK4),
**MINI**, **XL**.

The `--printer` flag also auto-sets `--bed-center` from the printer's known
bed dimensions (you can still override with an explicit `--bed-center`).

The start G-code includes mesh bed leveling at a safe probing temperature
(170 deg C or hotend temp, whichever is lower) and cooling fan during MBL for
PLA-like filaments (disabled for filaments requiring an enclosure like ABS/ASA).

#### Printer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--printer-url` | | PrusaLink URL (e.g. `http://192.168.1.100`) |
| `--api-key` | | PrusaLink API key |
| `--no-upload` | `false` | Skip uploading to printer |
| `--print-after-upload` | `false` | Start printing after upload |

#### Output Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | temp dir | Directory for output files |
| `--keep-files` | `false` | Keep intermediate STL and raw G-code |
| `--ascii-gcode` | `false` | Output ASCII `.gcode` instead of binary `.bgcode` |
| `--config` | auto-detect | Path to a TOML config file |
| `-v`, `--verbose` | `false` | Show detailed debug output |

### Examples

Direct drive extruder (typical PA range 0.02--0.10):

```bash
pressure-advance \
  --start-pa 0 --end-pa 0.10 --pa-step 0.01 \
  --no-upload --output-dir ./output
```

With printer-specific G-code for Prusa Core One:

```bash
pressure-advance \
  --start-pa 0 --end-pa 0.10 --pa-step 0.01 \
  --printer coreone \
  --no-upload --output-dir ./output
```

Bowden extruder (typical PA range 0.3--1.0):

```bash
pressure-advance \
  --start-pa 0.3 --end-pa 1.0 --pa-step 0.05 \
  --no-upload --output-dir ./output
```

PETG with custom temperatures:

```bash
pressure-advance \
  --start-pa 0 --end-pa 0.10 --pa-step 0.01 \
  --filament-type PETG \
  --nozzle-temp 240 --bed-temp 80 \
  --no-upload
```

With a 0.6mm nozzle (auto-sets 0.3mm layer height, 0.68mm extrusion width):

```bash
pressure-advance \
  --start-pa 0 --end-pa 0.10 --pa-step 0.01 \
  --nozzle-size 0.6 \
  --no-upload
```

Pattern method (chevron shapes instead of tower):

```bash
pressure-advance \
  --method pattern \
  --start-pa 0 --end-pa 0.10 --pa-step 0.005 \
  --no-upload --output-dir ./output
```

MK4S with ABS filament:

```bash
pressure-advance \
  --start-pa 0 --end-pa 0.08 --pa-step 0.01 \
  --printer mk4s --filament-type ABS \
  --no-upload --output-dir ./output
```

---

## GUI

A Streamlit browser GUI wraps all four CLI tools. Install and run:

```bash
pip install -e ".[gui]"
filament-calibrator-gui
```

The GUI opens in your browser and provides tabs for each calibration tool,
shared sidebar settings (filament type, printer, nozzle size, PrusaLink
upload), and a Results tab for merging calibration values into a PrusaSlicer
`.ini` config file.

---

## Development

Run tests:

```bash
pip install -e ".[dev]"
pytest tests/ --cov=src/filament_calibrator --cov-report=term-missing
```

100% statement coverage is required and enforced via `--cov-fail-under=100`.

## License

GPL-3.0-only
