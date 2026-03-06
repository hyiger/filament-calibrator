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
    """Test _pa_command() for different printer types."""

    def test_mini_uses_m900(self) -> None:
        assert _pa_command(0.04, "MINI") == "M900 K0.0400"

    def test_mini_case_insensitive(self) -> None:
        assert _pa_command(0.04, "mini") == "M900 K0.0400"

    def test_coreone_uses_m572(self) -> None:
        assert _pa_command(0.05, "COREONE") == "M572 S0.0500"

    def test_mk4s_uses_m572(self) -> None:
        assert _pa_command(0.03, "MK4S") == "M572 S0.0300"

    def test_xl_uses_m572(self) -> None:
        assert _pa_command(0.04, "XL") == "M572 S0.0400"


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

    def test_insert_m572_no_existing_pa(self) -> None:
        lines = ['start_filament_gcode = "G92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.04, "COREONE")
        assert len(result) == 1
        assert 'M572 S0.0400\\nG92 E0' in result[0]

    def test_replace_existing_m572(self) -> None:
        lines = ['start_filament_gcode = "M572 S0.0200\\nG92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.05, "COREONE")
        assert len(result) == 1
        assert "M572 S0.0500" in result[0]
        assert "M572 S0.0200" not in result[0]
        assert "G92 E0" in result[0]

    def test_insert_m900_for_mini(self) -> None:
        lines = ['start_filament_gcode = "G92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.06, "MINI")
        assert "M900 K0.0600" in result[0]

    def test_replace_existing_m900(self) -> None:
        lines = ['start_filament_gcode = "M900 K0.0200\\nG92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.07, "MINI")
        assert "M900 K0.0700" in result[0]
        assert "M900 K0.0200" not in result[0]

    def test_key_absent_appends(self) -> None:
        lines = ["temperature = 200"]
        result = _inject_pa_into_start_gcode(lines, 0.04, "COREONE")
        assert result[0] == "temperature = 200"
        assert result[-1] == "start_filament_gcode = M572 S0.0400"

    def test_key_absent_appends_mini(self) -> None:
        lines = ["temperature = 200"]
        result = _inject_pa_into_start_gcode(lines, 0.04, "MINI")
        assert result[-1] == "start_filament_gcode = M900 K0.0400"

    def test_unquoted_value(self) -> None:
        lines = ["start_filament_gcode = G92 E0"]
        result = _inject_pa_into_start_gcode(lines, 0.04, "COREONE")
        assert "M572 S0.0400" in result[0]
        assert "G92 E0" in result[0]

    def test_empty_value_quoted(self) -> None:
        lines = ['start_filament_gcode = ""']
        result = _inject_pa_into_start_gcode(lines, 0.04, "COREONE")
        assert 'M572 S0.0400' in result[0]

    def test_empty_value_unquoted(self) -> None:
        lines = ["start_filament_gcode = "]
        result = _inject_pa_into_start_gcode(lines, 0.04, "COREONE")
        assert "M572 S0.0400" in result[0]

    def test_preserves_other_lines(self) -> None:
        lines = [
            "# comment",
            'start_filament_gcode = "G92 E0"',
            "temperature = 200",
        ]
        result = _inject_pa_into_start_gcode(lines, 0.04, "COREONE")
        assert result[0] == "# comment"
        assert result[2] == "temperature = 200"

    def test_cross_replace_m900_with_m572(self) -> None:
        """Switching printer from Mini to CoreOne replaces M900 with M572."""
        lines = ['start_filament_gcode = "M900 K0.0200\\nG92 E0"']
        result = _inject_pa_into_start_gcode(lines, 0.04, "COREONE")
        assert "M572 S0.0400" in result[0]
        assert "M900" not in result[0]


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
            "extrusion_multiplier = 1\n"
        )
        results = CalibrationResults(
            temperature=215,
            max_volumetric_speed=12.5,
            pa_value=0.04,
            extrusion_multiplier=0.95,
            printer="COREONE",
        )
        merged = merge_results_into_ini(ini, results)
        assert "temperature = 215" in merged
        assert "first_layer_temperature = 215" in merged
        assert "filament_max_volumetric_speed = 12.5" in merged
        assert "M572 S0.0400" in merged
        assert "extrusion_multiplier = 0.95" in merged

    def test_all_values_mini(self) -> None:
        ini = (
            "temperature = 200\n"
            'start_filament_gcode = "G92 E0"\n'
        )
        results = CalibrationResults(
            temperature=215,
            pa_value=0.04,
            printer="MINI",
        )
        merged = merge_results_into_ini(ini, results)
        assert "M900 K0.0400" in merged

    def test_only_temperature(self) -> None:
        ini = "temperature = 200\nfirst_layer_temperature = 200\n"
        results = CalibrationResults(temperature=230)
        merged = merge_results_into_ini(ini, results)
        assert "temperature = 230" in merged
        assert "first_layer_temperature = 230" in merged
        assert "filament_max_volumetric_speed" not in merged
        assert "M572" not in merged
        assert "M900" not in merged

    def test_only_flow(self) -> None:
        ini = "filament_max_volumetric_speed = 8\n"
        results = CalibrationResults(max_volumetric_speed=15.0)
        merged = merge_results_into_ini(ini, results)
        assert "filament_max_volumetric_speed = 15.0" in merged

    def test_only_pa_mini(self) -> None:
        ini = 'start_filament_gcode = "G92 E0"\n'
        results = CalibrationResults(pa_value=0.06, printer="MINI")
        merged = merge_results_into_ini(ini, results)
        assert "M900 K0.0600" in merged

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
            extrusion_multiplier=0.97,
            printer="MK4S",
        )
        merged = merge_results_into_ini(ini, results)
        assert "temperature = 220" in merged
        assert "first_layer_temperature = 220" in merged
        assert "filament_max_volumetric_speed = 11.0" in merged
        assert "start_filament_gcode = M572 S0.0400" in merged
        assert "extrusion_multiplier = 0.97" in merged

    def test_only_em(self) -> None:
        ini = "extrusion_multiplier = 1\n"
        results = CalibrationResults(extrusion_multiplier=0.93)
        merged = merge_results_into_ini(ini, results)
        assert "extrusion_multiplier = 0.93" in merged

    def test_em_appended_when_missing(self) -> None:
        ini = "temperature = 200\n"
        results = CalibrationResults(extrusion_multiplier=1.02)
        merged = merge_results_into_ini(ini, results)
        assert "extrusion_multiplier = 1.02" in merged

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
            extrusion_multiplier=0.95,
            printer="COREONE",
        )
        summary = build_change_summary(results)
        assert "215 °C" in summary
        assert "12.5 mm³/s" in summary
        assert "M572 S0.0400" in summary
        assert "0.95" in summary
        assert "extrusion_multiplier" in summary

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

    def test_partial_pa_mini(self) -> None:
        results = CalibrationResults(pa_value=0.05, printer="MINI")
        summary = build_change_summary(results)
        assert "M900 K0.0500" in summary

    def test_partial_em_only(self) -> None:
        results = CalibrationResults(extrusion_multiplier=0.97)
        summary = build_change_summary(results)
        assert "0.97" in summary
        assert "extrusion_multiplier" in summary
        assert "temperature" not in summary.lower()
