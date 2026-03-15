# Quick Start Guide

**filament-calibrator** is a CLI tool suite for 3D printer filament
calibration on Prusa printers. It generates, slices, and uploads
calibration prints so you can dial in temperature, flow, pressure
advance, retraction, and more.

Full documentation: <https://github.com/hyiger/filament-calibrator>

---

## Prerequisites

**PrusaSlicer** must be installed and available on your `PATH`.
Download from [prusa3d.com](https://www.prusa3d.com/page/prusaslicer_424/).

A Prusa printer with **PrusaLink** enabled is needed only if you want to
upload G-code directly from the tool.

## Running the Standalone GUI

If you downloaded a pre-built binary from
[GitHub Releases](https://github.com/hyiger/filament-calibrator/releases),
extract the archive and run the `FilamentCalibrator` executable.

### macOS

Remove the quarantine attribute before running:

```bash
xattr -cr FilamentCalibrator
./FilamentCalibrator
```

### Linux

Make the file executable and run:

```bash
chmod +x FilamentCalibrator
./FilamentCalibrator
```

### Windows

Double-click `FilamentCalibrator.exe` or run it from PowerShell:

```powershell
.\FilamentCalibrator.exe
```

The GUI opens in your default browser.

## Installing from PyPI

If you prefer a PyPI install (requires **Python 3.10 or 3.12**):

```bash
# Recommended — uv installs its own Python, no prerequisites
uv tool install "filament-calibrator[gui]" --python 3.12

# Alternative
pipx install "filament-calibrator[gui]"
```

Then launch the GUI with:

```bash
filament-calibrator-gui
```

## CLI Tools

All eleven calibration commands are available on your PATH after
installing. Each generates a calibration print, slices it with
PrusaSlicer, and optionally uploads to your printer via PrusaLink.

| Command                | What it calibrates                           |
|------------------------|----------------------------------------------|
| `temperature-tower`    | Optimal printing temperature                 |
| `extrusion-multiplier` | Extrusion multiplier via wall thickness       |
| `volumetric-flow`      | Maximum volumetric flow rate                  |
| `pressure-advance`     | Pressure Advance / Linear Advance value       |
| `retraction-test`      | Retraction distance (stringing)               |
| `retraction-speed`     | Retraction speed                              |
| `shrinkage-test`       | Per-axis dimensional shrinkage (X/Y/Z)        |
| `tolerance-test`       | Hole and peg dimensional accuracy             |
| `bridging-test`        | Bridge quality at increasing span lengths     |
| `overhang-test`        | Overhang quality at increasing angles         |
| `cooling-test`         | Print quality at different fan speeds         |

Run any command with `--help` for full usage:

```bash
temperature-tower --help
```

## Basic Workflow

1. **Pick a calibration** — start with `temperature-tower`, then work
   through flow and retraction tests.
2. **Generate & slice** — run the command (or use the GUI). It creates
   an STL model, slices it with PrusaSlicer, and produces G-code.
3. **Print** — upload via `--upload` or copy the G-code file to your
   printer manually.
4. **Inspect & measure** — examine the print and (where applicable)
   measure with calipers.
5. **Apply results** — use the optimal values in your slicer profile,
   or let the GUI's Results tab export a PrusaSlicer config.

## Common Options

All commands share these options:

- `--filament-type` — filament preset (PLA, PETG, ABS, ASA, TPU, ...)
- `--nozzle-temp` / `--bed-temp` — override preset temperatures
- `--nozzle-size` — nozzle diameter in mm (default: 0.4)
- `--output-dir` — where to save generated files
- `--upload` — upload G-code to printer via PrusaLink
- `--printer-url` / `--api-key` — PrusaLink connection details
- `--ascii-gcode` — output text G-code instead of binary

## Configuration File

Save defaults in `~/.config/filament-calibrator/config.toml`:

```toml
filament_type = "PLA"
printer_url = "http://192.168.1.100"
api_key = "your-prusalink-api-key"
```

See [Configuration docs](https://github.com/hyiger/filament-calibrator/blob/main/docs/configuration.md)
for all available keys.

## Getting Help

- **Documentation:** <https://github.com/hyiger/filament-calibrator>
- **Issues:** <https://github.com/hyiger/filament-calibrator/issues>
- **GUI guide:** <https://github.com/hyiger/filament-calibrator/blob/main/docs/gui.md>
