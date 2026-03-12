[← Back to README](../README.md)

# Cooling Test

Generates a single cylindrical tower where fan speed is changed via `M106`
at each height level so the user can inspect print quality at different
cooling rates. PrusaSlicer's automatic fan management is disabled so the
M106 commands have full control.

## Quick Start

Test fan speed from 0% to 100% in 10% steps:

```bash
cooling-test --no-upload --output-dir ./output --keep-files
```

Upload directly to printer:

```bash
cooling-test \
  --start-fan 0 --end-fan 100 --fan-step 10 \
  --printer-url http://192.168.1.100 \
  --api-key YOUR_API_KEY
```

## How It Works

1. **Model generation** — CadQuery builds a single cylindrical tower on a
   rectangular base plate. The tower height is determined by the number of
   fan-speed levels times the level height.

2. **Slicing** — PrusaSlicer slices with standard settings (2 perimeters,
   15% infill). The slicer function forces `--cooling=0` to disable
   automatic fan speed management.

3. **Fan command insertion** — `M106 S<value>` commands are inserted at the
   G-code layer boundaries for each level. The S parameter is the PWM value
   (0--255), converted from the percentage.

4. **Upload** — Same PrusaLink upload path as the other tools.

## Interpreting the Print

Inspect the tower surface quality at each height level:

- **Too little cooling** — stringing, blobbing, poor overhangs, layer
  deformation (especially visible on small cross-sections like this tower).
- **Good cooling** — clean surfaces, crisp details, no warping.
- **Too much cooling** — layer adhesion issues, delamination, or warping
  (more common with ABS/ASA).

The lowest fan speed that produces acceptable surface quality is your optimal
setting. For PLA, 100% fan is typically fine. For ABS/ASA, 0--30% may be
needed to prevent warping and delamination. The tool prints a lookup table
mapping Z heights to fan speed percentages.

## CLI Reference

### Cooling Options

| Flag | Default | Description |
|------|---------|-------------|
| `--start-fan` | `0` | Starting fan speed percentage (0--100) |
| `--end-fan` | `100` | Ending fan speed percentage (0--100) |
| `--fan-step` | `10` | Fan speed percentage increment per level |

The fan range must be evenly divisible by `--fan-step`, `--end-fan` must
be at most 100, and the resulting number of levels cannot exceed 50.
`--start-fan` must be non-negative and `--end-fan` must be greater than
`--start-fan`.

### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type — sets nozzle temp, bed temp, and fan speed from preset |
| `--level-height` | `5.0` | Height per cooling level in mm |

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

Fine-grained test for ABS cooling (low fan range):

```bash
cooling-test \
  --start-fan 0 --end-fan 30 --fan-step 5 \
  --filament-type ABS --nozzle-temp 250 --bed-temp 100 \
  --no-upload
```

Narrowed range with finer steps:

```bash
cooling-test --start-fan 40 --end-fan 80 --fan-step 5 --no-upload
```

With a 0.6mm nozzle:

```bash
cooling-test --nozzle-size 0.6 --no-upload
```
