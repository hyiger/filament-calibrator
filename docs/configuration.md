[← Back to README](../README.md)

# Configuration

## Filament Presets

All eleven tools use presets from `gcode-lib` to set smart defaults for each filament
type. Known presets: **ABS**, **ASA**, **HIPS**, **PA**, **PA-CF**, **PC**,
**PCTG**, **PETG**, **PETG-CF**, **PLA**, **PLA-CF**, **PP**, **PPA**, **TPU**.

Each preset provides: recommended hotend temperature, bed temperature, fan
speed, retraction distance, safe temperature range (`temp_min`/`temp_max`),
print speed, and enclosure recommendation.

When you specify `--filament-type` (default `PLA`), the tool uses the preset
to set default temperatures and fan speed. All preset values can be overridden
with explicit CLI flags.

## TOML Config File

Save commonly reused settings in a TOML file so you don't have to pass them
on every run. To get started, copy the example file:

```bash
cp filament-calibrator.example.toml filament-calibrator.toml
```

Then edit it with your printer and slicer details:

```toml
# Printer connection (required for uploading)
printer-url = "http://192.168.1.100"
api-key = "your-prusalink-api-key"

# Printer model — generates printer-specific start/end G-code
# for pressure-advance (when no --config-ini is given).
# Supported: coreone, coreonel, mk4s, mini, xl
# printer = "coreone"

# Slicer setup (prusaslicer-path is only needed if PrusaSlicer is not
# installed in a standard location — the tool auto-detects it on PATH)
# prusaslicer-path = "/usr/bin/prusa-slicer"
# config-ini = "/path/to/printer-profile.ini"

# Bed centre in mm — default is 125,110 (Prusa MK-series 250×220 mm bed).
# Auto-set by printer if specified. For Prusa MINI, use 90,90.
# bed-center = "125,110"

# Nozzle size in mm — derives layer height (nozzle × 0.5) and
# extrusion width (nozzle × 1.125). Default: 0.4
# nozzle-size = 0.4

# Defaults
filament-type = "PLA"
output-dir = "./output"

# Temperature overrides — applied to all tools that accept these flags.
# These override the preset defaults but are in turn overridden by
# explicit CLI flags (--nozzle-temp, --bed-temp, --fan-speed).
# nozzle-temp = 215
# bed-temp = 60
# fan-speed = 100
```

All keys are optional — include only what you need. In particular,
`prusaslicer-path` can be omitted if PrusaSlicer is installed in a standard
location (e.g. `/usr/bin/prusa-slicer`, `/Applications/PrusaSlicer.app`, or
anywhere on your `PATH`).

The config file is shared between all eleven tools.

### Config file locations

The tools look for a config file in this order (first found wins):

| Priority | Location | Use case |
|----------|----------|----------|
| 1 | `--config <path>` | Explicit override |
| 2 | `./filament-calibrator.toml` | Per-project settings |
| 3 | `~/filament-calibrator.toml` | Home directory fallback |
| 4 | `~/.config/filament-calibrator/config.toml` | XDG user-wide defaults |

Config values are applied as defaults. CLI arguments usually override config
file values; if a CLI value is identical to the built-in default, the config
value may still apply.
