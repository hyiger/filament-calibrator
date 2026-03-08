# GUI

A Streamlit browser GUI wraps all six CLI tools. Install and run:

```bash
pip install -e ".[gui]"
filament-calibrator-gui
```

The GUI opens in your browser and provides tabs for each calibration tool,
shared sidebar settings (filament type, printer, nozzle size, PrusaLink
upload), and a Results tab for merging calibration values into a PrusaSlicer
`.ini` config file.
