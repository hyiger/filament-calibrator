[← Back to README](../README.md)

# Retraction Speed Test

Reuses the same two-tower model as the [Retraction Test](retraction-test.md),
but varies retraction **speed** instead of length. At each height level the
firmware retraction speed is changed via `M207 S<length> F<speed>` while
keeping the retraction length fixed, so the user can inspect stringing at each
height to find the optimal retraction speed.

## Quick Start

Test retraction speed from 20 to 60 mm/s in 5 mm/s steps:

```bash
retraction-speed \
  --start-speed 20 --end-speed 60 --speed-step 5 \
  --no-upload --output-dir ./output --keep-files
```

Upload directly to printer:

```bash
retraction-speed \
  --start-speed 20 --end-speed 60 --speed-step 5 \
  --printer-url http://192.168.1.100 \
  --api-key YOUR_API_KEY
```

## How It Works

1. **Model generation** — CadQuery builds two cylindrical towers on a shared
   rectangular base, spaced apart to force travel moves (same model as
   retraction-test).

2. **Slicing** — PrusaSlicer slices with `--use-firmware-retraction` so it
   emits G10/G11 commands. This allows M207 commands to control retraction
   at runtime.

3. **Speed command insertion** — `M207 S<length> F<speed>` commands are
   inserted at the G-code layer boundaries for each level. The retraction
   length stays fixed while the speed varies.

4. **Upload** — Same PrusaLink upload path as the other tools.

## Interpreting the Print

Inspect the stringing between the two towers at each height level. The level
with the least stringing (clean travel moves, no wisps) at the lowest
speed indicates your optimal retraction speed. Faster retraction generally
reduces stringing, but too fast can cause filament grinding. The tool prints
a lookup table mapping Z heights to retraction speeds.

## CLI Reference

### Retraction Speed Options

| Flag | Default | Description |
|------|---------|-------------|
| `--retraction-length` | `0.8` | Fixed retraction length in mm |
| `--start-speed` | `20.0` | Starting retraction speed in mm/s |
| `--end-speed` | `60.0` | Ending retraction speed in mm/s |
| `--speed-step` | `5.0` | Retraction speed increment per level in mm/s |

The retraction length must be positive. The speed range must be evenly
divisible by `--speed-step`, and the resulting number of levels cannot
exceed 50. `--start-speed` must be positive and `--end-speed` must be
greater than `--start-speed`.

### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type — sets nozzle temp, bed temp, and fan speed from preset |
| `--level-height` | `1.0` | Height per retraction speed level in mm |

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

Fine-tune retraction speed after finding optimal length:

```bash
retraction-speed \
  --retraction-length 0.8 \
  --start-speed 20 --end-speed 60 --speed-step 5 \
  --no-upload --output-dir ./output
```

Narrow range with finer steps:

```bash
retraction-speed \
  --retraction-length 0.8 \
  --start-speed 30 --end-speed 50 --speed-step 2 \
  --no-upload --output-dir ./output
```

PETG with custom temperatures:

```bash
retraction-speed \
  --retraction-length 1.0 \
  --start-speed 15 --end-speed 45 --speed-step 5 \
  --filament-type PETG \
  --nozzle-temp 240 --bed-temp 80 \
  --no-upload
```
