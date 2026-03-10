"""Tests for filament_calibrator.ini_writer — INI merging for calibration results."""
from __future__ import annotations

from filament_calibrator.ini_writer import (
    CalibrationResults,
    build_change_summary,
    merge_results_into_ini,
)


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

    def test_only_retraction(self) -> None:
        ini = "retract_length = 1.0\n"
        results = CalibrationResults(retraction_length=0.6)
        merged = merge_results_into_ini(ini, results)
        assert "retract_length = 0.6" in merged

    def test_retraction_appended_when_missing(self) -> None:
        ini = "temperature = 200\n"
        results = CalibrationResults(retraction_length=0.8)
        merged = merge_results_into_ini(ini, results)
        assert "retract_length = 0.8" in merged

    def test_only_xy_shrinkage(self) -> None:
        ini = "temperature = 200\n"
        results = CalibrationResults(xy_shrinkage=0.5)
        merged = merge_results_into_ini(ini, results)
        assert "shrinkage_compensation = 100.5%,100.5%,100.0%" in merged

    def test_only_z_shrinkage(self) -> None:
        ini = "temperature = 200\n"
        results = CalibrationResults(z_shrinkage=0.3)
        merged = merge_results_into_ini(ini, results)
        assert "shrinkage_compensation = 100.0%,100.0%,100.3%" in merged

    def test_both_shrinkage(self) -> None:
        ini = "temperature = 200\n"
        results = CalibrationResults(xy_shrinkage=0.5, z_shrinkage=0.3)
        merged = merge_results_into_ini(ini, results)
        assert "shrinkage_compensation = 100.5%,100.5%,100.3%" in merged

    def test_shrinkage_replaces_existing(self) -> None:
        ini = "shrinkage_compensation = 100%,100%,100%\n"
        results = CalibrationResults(xy_shrinkage=1.0, z_shrinkage=0.5)
        merged = merge_results_into_ini(ini, results)
        assert "shrinkage_compensation = 101.0%,101.0%,100.5%" in merged
        # Original value should be gone.
        assert "100%,100%,100%" not in merged

    def test_shrinkage_appended_when_missing(self) -> None:
        ini = "temperature = 200\n"
        results = CalibrationResults(xy_shrinkage=0.2)
        merged = merge_results_into_ini(ini, results)
        lines = merged.splitlines()
        assert lines[-1] == "shrinkage_compensation = 100.2%,100.2%,100.0%"

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

    def test_partial_retraction_only(self) -> None:
        results = CalibrationResults(retraction_length=0.6)
        summary = build_change_summary(results)
        assert "0.6 mm" in summary
        assert "retract_length" in summary
        assert "temperature" not in summary.lower()

    def test_partial_shrinkage_xy_only(self) -> None:
        results = CalibrationResults(xy_shrinkage=0.5)
        summary = build_change_summary(results)
        assert "100.5%, 100.5%, 100.0%" in summary
        assert "shrinkage_compensation" in summary
        assert "temperature" not in summary.lower()

    def test_partial_shrinkage_both(self) -> None:
        results = CalibrationResults(xy_shrinkage=0.5, z_shrinkage=0.3)
        summary = build_change_summary(results)
        assert "100.5%, 100.5%, 100.3%" in summary
        assert "shrinkage_compensation" in summary

    def test_all_set_includes_shrinkage(self) -> None:
        results = CalibrationResults(
            temperature=215,
            max_volumetric_speed=12.5,
            pa_value=0.04,
            extrusion_multiplier=0.95,
            retraction_length=0.6,
            xy_shrinkage=0.5,
            z_shrinkage=0.3,
            printer="COREONE",
        )
        summary = build_change_summary(results)
        assert "215 °C" in summary
        assert "12.5 mm³/s" in summary
        assert "M572 S0.0400" in summary
        assert "0.95" in summary
        assert "0.6 mm" in summary
        assert "100.5%, 100.5%, 100.3%" in summary
