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
- **[Retraction Speed](docs/retraction-speed.md)** — find the optimal retraction speed (varies speed while keeping length fixed)
- **[Shrinkage Test](docs/shrinkage.md)** — measure per-axis shrinkage (X/Y/Z) by printing a 3-axis calibration cross
- **[Tolerance Test](docs/tolerance-test.md)** — measure hole/peg dimensional accuracy with calipers
- **[Bridging Test](docs/bridging-test.md)** — evaluate bridge quality at increasing span lengths
- **[Overhang Test](docs/overhang-test.md)** — evaluate overhang quality at increasing angles (supports disabled)
- **[Cooling Test](docs/cooling-test.md)** — find optimal fan speed by varying cooling at each height level

## Quick Start

Install from PyPI (requires **Python 3.10 or 3.12** and **PrusaSlicer** on
your PATH):

```bash
uv tool install "filament-calibrator[gui]" --python 3.12
```

Or download a standalone GUI binary from
[Releases](https://github.com/hyiger/filament-calibrator/releases) — no
Python needed.

## Documentation

- **[Installation Guide](docs/installation.md)** — PyPI, standalone GUI,
  Windows, Raspberry Pi, conda, and source install options
- **[GUI User's Guide](docs/gui.md)** — walkthrough of the browser
  interface with screenshots
- **[Configuration](docs/configuration.md)** — TOML config file for saving
  printer URL, API key, filament type, and other defaults

## GUI

A [browser-based GUI](docs/gui.md) wraps all eleven tools:

```bash
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
