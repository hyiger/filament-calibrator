# Shrinkage Test

Generates a parametric 3-axis calibration cross, slices it with standard
settings, and uploads. Print the cross, measure each arm with calipers, and
calculate per-axis shrinkage:
`shrinkage % = (nominal − measured) / nominal × 100`.

## Quick Start

Generate a PLA shrinkage cross with default settings:

```bash
shrinkage-test --no-upload --output-dir ./output --keep-files
```

Upload directly to printer:

```bash
shrinkage-test \
  --printer-url http://192.168.1.100 \
  --api-key YOUR_API_KEY
```

## How It Works

1. **Model generation** — CadQuery builds a 3-axis cross: three perpendicular
   rectangular arms (X, Y, Z) meeting at a centre block, each 100 mm long with
   a 10 × 10 mm square cross-section. Square window cutouts at 20 mm intervals
   reduce material usage and print time. Embossed X/Y/Z labels identify each
   axis.

2. **Slicing** — PrusaSlicer slices with standard settings (3 perimeters,
   20% infill, 5 top / 4 bottom solid layers) for dimensional accuracy.

3. **Expected dimensions** — The tool prints the nominal arm length for each
   axis (default 100 mm).

4. **Upload** — Same PrusaLink upload path as the other tools.

## Interpreting the Print

Print the cross, then measure each arm length with digital calipers:

- **X arm** — horizontal arm labelled "X"
- **Y arm** — horizontal arm labelled "Y"
- **Z arm** — vertical arm labelled "Z"

Calculate per-axis shrinkage:

```
shrinkage_x = (nominal - measured_x) / nominal * 100
shrinkage_y = (nominal - measured_y) / nominal * 100
shrinkage_z = (nominal - measured_z) / nominal * 100
```

For example, if nominal is 100 mm and you measure X=99.2, Y=99.4, Z=99.0:

- X shrinkage = (100 − 99.2) / 100 × 100 = **0.8%**
- Y shrinkage = (100 − 99.4) / 100 × 100 = **0.6%**
- Z shrinkage = (100 − 99.0) / 100 × 100 = **1.0%**

Materials like ABS, ASA, Nylon, and PC typically show 0.5–2% shrinkage.
PLA and PETG usually show minimal shrinkage (< 0.5%).

## CLI Reference

### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type (preset name or custom) |
| `--arm-length` | `100.0` | Length of each arm in mm |

### Nozzle Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-size` | `0.4` | Nozzle diameter in mm — derives layer height (`nozzle × 0.5`) and extrusion width (`nozzle × 1.125`) |
| `--nozzle-high-flow` | `false` | Nozzle is a high-flow variant (sets F flag in M862.1) |
| `--nozzle-hardened` | `false` | Nozzle is hardened/abrasive-resistant (sets A flag in M862.1) |

### Slicer Options

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

### Printer Options

| Flag | Default | Description |
|------|---------|-------------|
| `--printer-url` | | PrusaLink URL (e.g. `http://192.168.1.100`) |
| `--api-key` | | PrusaLink API key |
| `--no-upload` | `false` | Skip uploading to printer |
| `--print-after-upload` | `false` | Start printing after upload |

### Output Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | temp dir | Directory for output files |
| `--keep-files` | `false` | Keep intermediate STL and raw G-code |
| `--ascii-gcode` | `false` | Output ASCII `.gcode` instead of binary `.bgcode` |
| `--config` | auto-detect | Path to a TOML config file |
| `-v`, `--verbose` | `false` | Show detailed debug output |

## Examples

ABS with custom temperature (ABS typically shrinks 0.5–1%):

```bash
shrinkage-test --filament-type ABS --nozzle-temp 250 --bed-temp 100 --no-upload
```

With a 0.6mm nozzle (auto-sets 0.3mm layer height, 0.68mm extrusion width):

```bash
shrinkage-test --nozzle-size 0.6 --no-upload
```

Custom arm length (shorter arms for faster print):

```bash
shrinkage-test --arm-length 80 --no-upload
```
