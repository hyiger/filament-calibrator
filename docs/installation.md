# Installation

## Prerequisites

- **PrusaSlicer** installed and available on your `PATH` (or provide
  `--prusaslicer-path`). Download from
  [prusa3d.com](https://www.prusa3d.com/page/prusaslicer_424/).
- A Prusa printer with **PrusaLink** enabled (only needed for uploading).

## Install from PyPI

The easiest way to install. Requires **Python 3.10 or 3.12** (see
[note on Python versions](#python-version-compatibility) below).

```bash
# Recommended — uv installs its own Python, no prerequisites
uv tool install filament-calibrator

# Alternative — requires Python already installed
pipx install filament-calibrator

# Or with plain pip in a virtual environment
pip install filament-calibrator
```

This makes the `temperature-tower`, `extrusion-multiplier`, `volumetric-flow`,
`pressure-advance`, `retraction-test`, and `shrinkage-test` commands available
on your PATH.

To include the browser GUI:

```bash
uv tool install "filament-calibrator[gui]"
# or: pipx install "filament-calibrator[gui]"
```

## Standalone GUI (no Python required)

Download a pre-built binary for your platform from the
[GitHub Releases](https://github.com/hyiger/filament-calibrator/releases) page.
Extract the archive and run the `FilamentCalibrator` executable — it opens the
Streamlit GUI in your browser.

Available for Linux (x86_64), macOS (ARM64 and Intel), and Windows (x86_64).

> **macOS note:** Unsigned binaries are blocked by Gatekeeper. Right-click the
> app and select "Open" to bypass the warning on first launch.

## Install from source

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

The `temperature-tower`, `extrusion-multiplier`, `volumetric-flow`,
`pressure-advance`, `retraction-test`, and `shrinkage-test` commands are
available whenever the venv is active. To reactivate later, run
`source .venv/bin/activate` from the project directory.

## Python version compatibility

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

## Raspberry Pi (Linux ARM64)

The PyPI wheels for `cadquery-ocp` don't include Linux ARM64 builds, so
`pip install` and `uv tool install` won't work on a Raspberry Pi. Use
[Miniforge](https://github.com/conda-forge/miniforge) (conda-forge for ARM)
instead — conda-forge builds OCP for `linux-aarch64`.

**1. Install Miniforge:**

```bash
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh
bash Miniforge3-Linux-aarch64.sh
```

Accept the defaults and say **yes** when asked to initialize conda in your
shell, then restart your shell:

```bash
source ~/.bashrc
```

**2. Create an environment with CadQuery and install filament-calibrator:**

```bash
conda create -n filcal python=3.12 cadquery -c conda-forge
conda activate filcal
pip install "filament-calibrator[gui]"
```

Since CadQuery and OCP are already installed by conda, pip will skip those
dependencies and install the rest (gcode-lib, streamlit, etc.).

**3. Run:**

```bash
conda activate filcal
temperature-tower --help
filament-calibrator-gui
```

You need to `conda activate filcal` each time before using the tools.

> **Note:** PrusaSlicer is also required on your PATH. ARM64 `.AppImage`
> builds are available from
> [prusa3d.com](https://www.prusa3d.com/page/prusaslicer_424/).

## Conda alternative

If pip installation doesn't work on other platforms, CadQuery can also be
installed via conda-forge:

```bash
conda create -n filament-cal python=3.12
conda activate filament-cal
mamba install -c conda-forge cadquery
pip install -e .
```

> **Note:** Install conda packages first, then pip packages. See the
> [Anaconda docs](https://www.anaconda.com/blog/using-pip-in-a-conda-environment)
> for details on mixing conda and pip.
