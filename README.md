# filament-calibrator

[![Tests](https://github.com/hyiger/filament-calibrator/actions/workflows/test.yml/badge.svg)](https://github.com/hyiger/filament-calibrator/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/filament-calibrator)](https://pypi.org/project/filament-calibrator/)

CLI tool suite for 3D printer filament calibration on Prusa printers.

## Calibration Tools

- **[Temperature Tower](docs/temperature-tower.md)** — find the optimal printing temperature for a filament
- **[Extrusion Multiplier](docs/extrusion-multiplier.md)** — measure wall thickness to calculate the correct extrusion multiplier
- **[Volumetric Flow](docs/volumetric-flow.md)** — determine maximum volumetric flow rate for a filament/hotend combination
- **[Pressure Advance](docs/pressure-advance.md)** — find the optimal PA/Linear Advance value (tower or chevron pattern method)
- **[Retraction Test](docs/retraction-test.md)** — find the optimal retraction distance by inspecting stringing between two towers
- **[Shrinkage Test](docs/shrinkage.md)** — measure per-axis shrinkage (X/Y/Z) by printing a 3-axis calibration cross

## Quick Start

Install from PyPI (requires **Python 3.10 or 3.12** and **PrusaSlicer** on
your PATH):

```bash
uv tool install filament-calibrator
```

Or download a standalone GUI binary from
[Releases](https://github.com/hyiger/filament-calibrator/releases) — no
Python needed.

See the full [installation guide](docs/installation.md) for all options.

## Configuration

Save printer URL, API key, filament type, and other defaults in a
[TOML config file](docs/configuration.md) to avoid repeating them on every
run.

## GUI

A [Streamlit browser GUI](docs/gui.md) wraps all six tools:

```bash
pip install -e ".[gui]"
filament-calibrator-gui
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ --cov=src/filament_calibrator --cov-report=term-missing \
  --cov-fail-under=100
```

100% statement coverage is enforced.

## License

GPL-3.0-only
