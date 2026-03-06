"""Tests for filament_calibrator.ini_writer — INI merging for calibration results."""
from __future__ import annotations

from filament_calibrator.ini_writer import (
    CalibrationResults,
    _inject_pa_into_start_gcode,
    _pa_command,
    _replace_ini_value,
    build_change_summary,
    merge_results_into_ini,
)


# ---------------------------------------------------------------------------
# _pa_command
# ---------------------------------------------------------------------------

class TestPaCommand:
    """Test _pa_command() for both firmware types."""

    def test_marlin(self) -> None:
        assert _pa_command(0.04, "marlin") == "M900 K0.0400"

    def test_klipper(self) -> None:
        assert _pa_command(0.05, "klipper") == "SET_PRESSURE_ADVANCE ADVANCE=0.0500"


# ---------------------------------------------------------------------------
# _replace_ini_value
# ---------------------------------------------------------------------------

class TestReplaceIniValue:
    """Test _replace_ini_value() line-by-line replacement."""

    def test_key_found(self) -> None:
        lines = ["temperature = 200", "bed_temperature = 60"]
        result, found = _replace_ini_value(lines, "temperature", "215")
        assert found is True
        assert result == ["temperature = 215", "bed_temperature = 60"]

    def test_key_not_found(self) -> None:
        lines = ["bed_temperature = 60"]
        result, found = _replace_ini_value(lines, "temperature", "215")
        assert found is False
        assert result == ["bed_temperature = 60"]

    def test_preserves_whitespace(self) -> None:
        lines = ["  temperature  =  200"]
        result, found = _replace_ini_value(lines, "temperature", "215")
        assert found is True
        assert result == ["  temperature  =  215"]

    def test_replaces_only_first(self) -> None:
        lines = ["temperature = 200", "temperature = 210"]
        result, found = _replace_ini_value(lines, "temperature", "215")
        assert found is True
        assert result == ["temperature = 215", "temperature = 210"]

    def test_empty_lines(self) -> None:
        lines: list[str] = []
        result, found = _replace_ini_value(lines, "temperature", "215")
        assert found is False
        assert result == []


# ---------------------------------------------------------------------------
# _inject_pa_into_start_gcode
# ---------------------------------------------------------------------------

class TestInjectPaIntoStartGcode:
    """Test _inject_pa_into_start_gcode() PA injection."""

    def test_insert_marlin_no_existing_pa(self) -> None:
        lines = ['start_filament_gcode = "G92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.04, "marlin")
        assert len(result) == 1
        assert 'M900 K0.0400\\nG92 E0' in result[0]

    def test_replace_existing_marlin(self) -> None:
        lines = ['start_filament_gcode = "M900 K0.0200\\nG92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.05, "marlin")
        assert len(result) == 1
        assert "M900 K0.0500" in result[0]
        assert "M900 K0.0200" not in result[0]
        assert "G92 E0" in result[0]

    def test_insert_klipper(self) -> None:
        lines = ['start_filament_gcode = "G92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.06, "klipper")
        assert "SET_PRESSURE_ADVANCE ADVANCE=0.0600" in result[0]

    def test_replace_existing_klipper(self) -> None:
        lines = [
            'start_filament_gcode = "'
            'SET_PRESSURE_ADVANCE ADVANCE=0.0200\\nG92 E0"'
        ]
        result = _inject_pa_into_start_gcode(lines, 0.07, "klipper")
        assert "SET_PRESSURE_ADVANCE ADVANCE=0.0700" in result[0]
        assert "SET_PRESSURE_ADVANCE ADVANCE=0.0200" not in result[0]

    def test_key_absent_appends(self) -> None:
        lines = ["temperature = 200"]
        result = _inject_pa_into_start_gcode(lines, 0.04, "marlin")
        assert result[0] == "temperature = 200"
        assert result[-1] == "start_filament_gcode = M900 K0.0400"

    def test_unquoted_value(self) -> None:
        lines = ["start_filament_gcode = G92 E0"]
        result = _inject_pa_into_start_gcode(lines, 0.04, "marlin")
        assert "M900 K0.0400" in result[0]
        assert "G92 E0" in result[0]

    def test_empty_value_quoted(self) -> None:
        lines = ['start_filament_gcode = ""']
        result = _inject_pa_into_start_gcode(lines, 0.04, "marlin")
        assert 'M900 K0.0400' in result[0]

    def test_empty_value_unquoted(self) -> None:
        lines = ["start_filament_gcode = "]
        result = _inject_pa_into_start_gcode(lines, 0.04, "marlin")
        assert "M900 K0.0400" in result[0]

    def test_preserves_other_lines(self) -> None:
        lines = [
            "# comment",
            'start_filament_gcode = "G92 E0"',
            "temperature = 200",
        ]
        result = _inject_pa_into_start_gcode(lines, 0.04, "marlin")
        assert result[0] == "# comment"
        assert result[2] == "temperature = 200"


# ---------------------------------------------------------------------------
# merge_results_into_ini
# ---------------------------------------------------------------------------

class TestMergeResultsIntoIni:
    """Test merge_results_into_ini() end-to-end merging."""

    def test_all_values_set(self) -> None:
        ini = (
            "temperature = 200\n"
            "first_layer_temperature = 200\n"
            "filament_max_volumetric_speed = 10\n"
            'start_filament_gcode = "G92 E0"\n'
        )
        results = CalibrationResults(
            temperature=215,
            max_volumetric_speed=12.5,
            pa_value=0.04,
            pa_firmware="marlin",
        )
        merged = merge_results_into_ini(ini, results)
        assert "temperature = 215" in merged
        assert "first_layer_temperature = 215" in merged
        assert "filament_max_volumetric_speed = 12.5" in merged
        assert "M900 K0.0400" in merged

    def test_only_temperature(self) -> None:
        ini = "temperature = 200\nfirst_layer_temperature = 200\n"
        results = CalibrationResults(temperature=230)
        merged = merge_results_into_ini(ini, results)
        assert "temperature = 230" in merged
        assert "first_layer_temperature = 230" in merged
        assert "filament_max_volumetric_speed" not in merged
        assert "M900" not in merged

    def test_only_flow(self) -> None:
        ini = "filament_max_volumetric_speed = 8\n"
        results = CalibrationResults(max_volumetric_speed=15.0)
        merged = merge_results_into_ini(ini, results)
        assert "filament_max_volumetric_speed = 15.0" in merged

    def test_only_pa(self) -> None:
        ini = 'start_filament_gcode = "G92 E0"\n'
        results = CalibrationResults(pa_value=0.06, pa_firmware="klipper")
        merged = merge_results_into_ini(ini, results)
        assert "SET_PRESSURE_ADVANCE ADVANCE=0.0600" in merged

    def test_none_set(self) -> None:
        ini = "temperature = 200\n"
        results = CalibrationResults()
        merged = merge_results_into_ini(ini, results)
        assert merged == "temperature = 200\n"

    def test_missing_keys_appended(self) -> None:
        ini = "# minimal config\n"
        results = CalibrationResults(
            temperature=220,
            max_volumetric_speed=11.0,
            pa_value=0.04,
            pa_firmware="marlin",
        )
        merged = merge_results_into_ini(ini, results)
        assert "temperature = 220" in merged
        assert "first_layer_temperature = 220" in merged
        assert "filament_max_volumetric_speed = 11.0" in merged
        assert "start_filament_gcode = M900 K0.0400" in merged

    def test_empty_input(self) -> None:
        results = CalibrationResults()
        merged = merge_results_into_ini("", results)
        assert merged == ""


# ---------------------------------------------------------------------------
# build_change_summary
# ---------------------------------------------------------------------------

class TestBuildChangeSummary:
    """Test build_change_summary() markdown output."""

    def test_all_set(self) -> None:
        results = CalibrationResults(
            temperature=215,
            max_volumetric_speed=12.5,
            pa_value=0.04,
            pa_firmware="marlin",
        )
        summary = build_change_summary(results)
        assert "215 °C" in summary
        assert "12.5 mm³/s" in summary
        assert "M900 K0.0400" in summary

    def test_none_set(self) -> None:
        results = CalibrationResults()
        summary = build_change_summary(results)
        assert "No changes" in summary

    def test_partial_temperature_only(self) -> None:
        results = CalibrationResults(temperature=230)
        summary = build_change_summary(results)
        assert "230 °C" in summary
        assert "volumetric" not in summary
        assert "Pressure" not in summary

    def test_partial_flow_only(self) -> None:
        results = CalibrationResults(max_volumetric_speed=14.0)
        summary = build_change_summary(results)
        assert "14.0 mm³/s" in summary
        assert "temperature" not in summary.lower()

    def test_partial_pa_klipper(self) -> None:
        results = CalibrationResults(pa_value=0.05, pa_firmware="klipper")
        summary = build_change_summary(results)
        assert "SET_PRESSURE_ADVANCE ADVANCE=0.0500" in summary
