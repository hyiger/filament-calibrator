[← Back to README](../README.md)

# Bridging Test

Generates a row of pillar pairs with flat bridges at increasing span
lengths. No G-code command insertion is needed — the user inspects bridge
quality at each span to determine the printer's maximum bridging capability.

## Quick Start

Test bridge spans from 10 to 60 mm:

```bash
bridging-test --no-upload --output-dir ./output --keep-files
```

Custom spans:

```bash
bridging-test --spans 15,25,35,45,55 --no-upload --output-dir ./output
```

## How It Works

1. **Model generation** — CadQuery builds pairs of rectangular pillars on a
   shared base plate. Each pair is spaced at the specified span distance, and
   a flat bridge connects the tops of each pair.

2. **Slicing** — PrusaSlicer slices with standard settings (2 perimeters,
   15% infill). No special slicer flags are required.

3. **Upload** — Same PrusaLink upload path as the other tools.

## Interpreting the Print

Inspect the underside of each bridge:

- **Good bridge** — smooth, flat underside with no sagging or drooping.
- **Marginal bridge** — slight sagging visible but still structurally sound.
- **Failed bridge** — significant drooping, gaps, or detachment.

The longest span with an acceptable bridge indicates your printer's bridging
limit at the current settings. Bridge quality depends on cooling (fan speed),
temperature, and print speed.

## CLI Reference

### Model Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filament-type` | `PLA` | Filament type — sets nozzle temp, bed temp, and fan speed from preset |
| `--spans` | `10,20,30,40,50,60` | Comma-separated span distances between pillar pairs in mm |
| `--pillar-height` | `15.0` | Height of bridge pillars in mm |

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

Short spans for small printers:

```bash
bridging-test --spans 5,10,15,20,25 --no-upload
```

Long spans to stress-test bridging:

```bash
bridging-test --spans 30,40,50,60,70,80 --no-upload
```

PETG with custom temperatures:

```bash
bridging-test --filament-type PETG --nozzle-temp 240 --bed-temp 80 --no-upload
```
