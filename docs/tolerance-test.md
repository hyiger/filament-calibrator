[← Back to README](../README.md)

# Tolerance Test

Generates a flat plate with circular through-holes and matching cylindrical
pegs at specified diameters. The user prints the specimen, measures holes
and pegs with calipers, and calculates dimensional accuracy to understand
how much the printer over- or under-extrudes in the XY plane.

## Quick Start

Test holes and pegs at 3, 5, 8, 10, 12, 15 mm:

```bash
tolerance-test --no-upload --output-dir ./output --keep-files
```

Custom diameters:

```bash
tolerance-test --diameters 4,6,8,10,12 --no-upload --output-dir ./output
```

## How It Works

1. **Model generation** — CadQuery builds a flat plate with a row of circular
   through-holes at the specified diameters and a matching row of cylindrical
   pegs below. Each peg sits on a thin base for bed adhesion.

2. **Slicing** — PrusaSlicer slices with dimensional-accuracy settings
   (3 perimeters, 20% infill, 5 top / 4 bottom solid layers) matching the
   shrinkage test for consistency.

3. **Upload** — Same PrusaLink upload path as the other tools.

## Interpreting the Print

Measure each hole and peg diameter with digital calipers:

- **Holes smaller than nominal** — the printer is over-extruding or has
  positive XY compensation. Holes are typically undersized on FDM printers.
- **Pegs larger than nominal** — same root cause as undersized holes.
- **Consistent offset** — if all holes are 0.2 mm smaller and all pegs
  0.2 mm larger, apply an XY contour compensation of -0.1 mm in your
  slicer settings.

For functional parts that need to fit together, knowing the dimensional
offset lets you adjust your CAD models or slicer compensation to achieve
accurate dimensions.

## CLI Reference

### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type — sets nozzle temp, bed temp, and fan speed from preset |
| `--diameters` | `3,5,8,10,12,15` | Comma-separated hole and peg diameters in mm |

### Nozzle Options

| Flag | Default | Description |
|------|---------|-------------|
| `--nozzle-size` | `0.4` | Nozzle diameter in mm — derives layer height (`nozzle × 0.5`) and extrusion width (`nozzle × 1.125`) |
| `--nozzle-high-flow` | `false` | Nozzle is a high-flow variant |
| `--nozzle-hardened` | `false` | Nozzle is hardened/abrasive-resistant |

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

Small diameters for precision parts:

```bash
tolerance-test --diameters 2,3,4,5,6 --no-upload
```

ABS (typically has more dimensional variation):

```bash
tolerance-test --filament-type ABS --nozzle-temp 250 --bed-temp 100 --no-upload
```

With a 0.6mm nozzle:

```bash
tolerance-test --nozzle-size 0.6 --no-upload
```
