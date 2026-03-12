[← Back to README](../README.md)

# Overhang Test

Generates a back wall with angled ramp surfaces at increasing overhang
angles from vertical. Supports are always disabled so the user can evaluate
overhang quality at each angle to determine the printer's maximum overhang
capability.

## Quick Start

Test overhang angles from 20° to 70°:

```bash
overhang-test --no-upload --output-dir ./output --keep-files
```

Custom angles:

```bash
overhang-test --angles 30,40,45,50,55,60 --no-upload --output-dir ./output
```

## How It Works

1. **Model generation** — CadQuery builds a tall back wall with angled
   surface slabs protruding from the front face. Each slab is rotated to
   the specified overhang angle from vertical. Slab length is automatically
   capped so no surface descends below the base plate.

2. **Slicing** — PrusaSlicer slices with standard settings (2 perimeters,
   15% infill). The slicer function forces `--support-material=0` to disable
   supports entirely.

3. **Upload** — Same PrusaLink upload path as the other tools.

## Interpreting the Print

Inspect the underside of each angled surface:

- **0° (vertical)** — flush with the wall, trivial for any printer.
- **45°** — a common practical limit for most FDM printers.
- **60°--70°** — challenging; quality depends on cooling and material.
- **90° (horizontal)** — a full bridge overhang.

Look for:
- **Clean surface** — smooth underside, no sagging or curling.
- **Rough surface** — some drooping or rough texture on the underside.
- **Failed surface** — severe sagging, detachment, or spaghetti.

The steepest angle with an acceptable underside is your printer's maximum
overhang angle. Overhang quality depends heavily on cooling (fan speed),
temperature, and print speed.

## CLI Reference

### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type — sets nozzle temp, bed temp, and fan speed from preset |
| `--angles` | `20,25,30,35,40,45,50,55,60,65,70` | Comma-separated overhang angles from vertical in degrees |

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

Focused test around the 45° threshold:

```bash
overhang-test --angles 35,40,42,45,48,50,55 --no-upload
```

ABS (typically needs lower angles due to warping):

```bash
overhang-test --filament-type ABS --nozzle-temp 250 --bed-temp 100 --no-upload
```

With a 0.6mm nozzle:

```bash
overhang-test --nozzle-size 0.6 --no-upload
```
