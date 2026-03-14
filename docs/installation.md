[← Back to README](../README.md)

# Installation

## Prerequisites

- **PrusaSlicer** installed and available on your `PATH` (or provide
  `--prusaslicer-path`). Download from
  [prusa3d.com](https://www.prusa3d.com/page/prusaslicer_424/).
- A Prusa printer with **PrusaLink** enabled (only needed for uploading).

## Install from PyPI

The easiest way to install. Recommended on **Python 3.10 or 3.12** (see
[note on Python versions](#python-version-compatibility) below).

```bash
# Recommended — uv installs its own Python, no prerequisites
uv tool install filament-calibrator

# Alternative — requires Python already installed
pipx install filament-calibrator

# Or with plain pip in a virtual environment
pip install filament-calibrator
```

This makes all eleven calibration commands available on your PATH:
`temperature-tower`, `extrusion-multiplier`, `volumetric-flow`,
`pressure-advance`, `retraction-test`, `retraction-speed`,
`shrinkage-test`, `bridging-test`, `overhang-test`, `tolerance-test`,
and `cooling-test`.

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

Available for Linux (x86_64 and ARM64), macOS (ARM64), and Windows (x86_64).

> **macOS note:** Downloaded binaries are quarantined by Gatekeeper. Remove
> the quarantine attribute before running:
>
> ```bash
> xattr -cr ~/Downloads/FilamentCalibrator
> ```

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

All eleven calibration commands are available whenever the venv is active.
To reactivate later, run `source .venv/bin/activate` from the project
directory.

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

## Windows 11

**1. Install uv:**

Open PowerShell and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen PowerShell after installation.

**2. Install PrusaSlicer:**

Download and install PrusaSlicer from
[prusa3d.com](https://www.prusa3d.com/page/prusaslicer_424/). The installer
adds it to your PATH automatically.

**3. Install filament-calibrator:**

```powershell
uv tool install "filament-calibrator[gui]" --python 3.12
```

The `--python 3.12` flag tells uv to download and use Python 3.12, which
has `cadquery-ocp` wheels available. Without it, uv may pick a Python
version that lacks binary wheels (see
[Python version compatibility](#python-version-compatibility)).

**4. Run:**

```powershell
filament-calibrator-gui
```

All eleven CLI tools are also available in any PowerShell or Command
Prompt window.

> **Alternative — standalone GUI:** If you prefer not to install Python at
> all, download the Windows build from
> [GitHub Releases](https://github.com/hyiger/filament-calibrator/releases),
> extract the zip, and run `FilamentCalibrator.exe`.

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
pip install "ezdxf>=1.0,<1.4"
pip install "filament-calibrator[gui]"
```

The `ezdxf` upgrade is needed because conda-forge installs a version that is
too old for CadQuery's DXF exporter. After that, pip installs
filament-calibrator and its remaining dependencies (gcode-lib, streamlit, etc.).

**3. Run:**

```bash
conda activate filcal
temperature-tower --help
filament-calibrator-gui
```

You need to `conda activate filcal` each time before using the tools.

**4. Install PrusaSlicer:**

PrusaSlicer is required for slicing. On Raspberry Pi OS, install it via
[Flatpak](https://flatpak.org/):

```bash
sudo apt install flatpak
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub com.prusa3d.PrusaSlicer
```

Then create a symlink so filament-calibrator can find it (shell aliases
don't work with subprocess calls):

```bash
sudo ln -s /var/lib/flatpak/exports/bin/com.prusa3d.PrusaSlicer /usr/local/bin/prusaslicer
```

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
