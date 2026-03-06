"""Tests for filament_calibrator.ini_parser."""
from __future__ import annotations

import pytest

from filament_calibrator.ini_parser import (
    _first_value,
    _parse_bed_shape,
    _parse_extrusion_width,
    _parse_float,
    _parse_int,
    parse_prusaslicer_ini,
)


# ---------------------------------------------------------------------------
# _first_value
# ---------------------------------------------------------------------------

class TestFirstValue:
    """Test _first_value() semicolon splitting."""

    def test_single_value(self) -> None:
        assert _first_value("0.4") == "0.4"

    def test_semicolon_delimited(self) -> None:
        assert _first_value("0.4;0.6") == "0.4"

    def test_with_spaces(self) -> None:
        assert _first_value(" 0.4 ; 0.6 ") == "0.4"

    def test_empty_string(self) -> None:
        assert _first_value("") == ""

    def test_multiple_semicolons(self) -> None:
        assert _first_value("210;220;230") == "210"


# ---------------------------------------------------------------------------
# _parse_float
# ---------------------------------------------------------------------------

class TestParseFloat:
    """Test _parse_float() value extraction."""

    def test_valid_float(self) -> None:
        assert _parse_float("0.4") == 0.4

    def test_valid_int_as_float(self) -> None:
        assert _parse_float("210") == 210.0

    def test_semicolon_takes_first(self) -> None:
        assert _parse_float("0.4;0.6") == 0.4

    def test_invalid_string(self) -> None:
        assert _parse_float("abc") is None

    def test_empty_string(self) -> None:
        assert _parse_float("") is None


# ---------------------------------------------------------------------------
# _parse_int
# ---------------------------------------------------------------------------

class TestParseInt:
    """Test _parse_int() value extraction."""

    def test_valid_int(self) -> None:
        assert _parse_int("210") == 210

    def test_truncates_float(self) -> None:
        assert _parse_int("210.7") == 210

    def test_semicolon_takes_first(self) -> None:
        assert _parse_int("215;220") == 215

    def test_invalid_string(self) -> None:
        assert _parse_int("abc") is None

    def test_empty_string(self) -> None:
        assert _parse_int("") is None


# ---------------------------------------------------------------------------
# _parse_extrusion_width
# ---------------------------------------------------------------------------

class TestParseExtrusionWidth:
    """Test _parse_extrusion_width() edge cases."""

    def test_zero_means_auto(self) -> None:
        assert _parse_extrusion_width("0") is None

    def test_empty_means_auto(self) -> None:
        assert _parse_extrusion_width("") is None

    def test_percentage_returns_none(self) -> None:
        assert _parse_extrusion_width("105%") is None

    def test_valid_mm_value(self) -> None:
        assert _parse_extrusion_width("0.45") == 0.45

    def test_negative_returns_none(self) -> None:
        assert _parse_extrusion_width("-0.1") is None

    def test_invalid_string(self) -> None:
        assert _parse_extrusion_width("abc") is None

    def test_semicolon_takes_first(self) -> None:
        assert _parse_extrusion_width("0.45;0.50") == 0.45


# ---------------------------------------------------------------------------
# _parse_bed_shape
# ---------------------------------------------------------------------------

class TestParseBedShape:
    """Test _parse_bed_shape() center computation."""

    def test_standard_rectangle(self) -> None:
        assert _parse_bed_shape("0x0,250x0,250x210,0x210") == "125,105"

    def test_prusa_mk4_bed(self) -> None:
        assert _parse_bed_shape("0x0,250x0,250x220,0x220") == "125,110"

    def test_offset_origin(self) -> None:
        # Bed not starting at origin.
        assert _parse_bed_shape("10x10,210x10,210x210,10x210") == "110,110"

    def test_malformed_returns_none(self) -> None:
        assert _parse_bed_shape("garbage") is None

    def test_empty_returns_none(self) -> None:
        assert _parse_bed_shape("") is None

    def test_partial_corner(self) -> None:
        assert _parse_bed_shape("0x0,250x0,250") is None


# ---------------------------------------------------------------------------
# parse_prusaslicer_ini (integration)
# ---------------------------------------------------------------------------

class TestParsePrusaslicerIni:
    """Test the main parse_prusaslicer_ini() entry point."""

    def test_flat_file_all_keys(self, tmp_path) -> None:
        """A flat file (no section headers) with all recognised keys."""
        ini = tmp_path / "config.ini"
        ini.write_text(
            "nozzle_diameter = 0.4\n"
            "temperature = 215\n"
            "bed_temperature = 60\n"
            "max_fan_speed = 100\n"
            "layer_height = 0.2\n"
            "extrusion_width = 0.45\n"
            "bed_shape = 0x0,250x0,250x210,0x210\n"
            "printer_model = MK4S\n"
        )
        result = parse_prusaslicer_ini(str(ini))
        assert result["nozzle_diameter"] == 0.4
        assert result["nozzle_temp"] == 215
        assert result["bed_temp"] == 60
        assert result["fan_speed"] == 100
        assert result["layer_height"] == 0.2
        assert result["extrusion_width"] == 0.45
        assert result["bed_center"] == "125,105"
        assert result["printer_model"] == "MK4S"

    def test_sectioned_file(self, tmp_path) -> None:
        """A file with PrusaSlicer-style section headers."""
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[printer:MK4S]\n"
            "nozzle_diameter = 0.6\n"
            "bed_shape = 0x0,250x0,250x220,0x220\n"
            "printer_model = MK4S\n"
            "\n"
            "[filament:PLA]\n"
            "temperature = 210\n"
            "bed_temperature = 55\n"
            "max_fan_speed = 100\n"
            "\n"
            "[print:Quality]\n"
            "layer_height = 0.15\n"
            "extrusion_width = 0.68\n"
        )
        result = parse_prusaslicer_ini(str(ini))
        assert result["nozzle_diameter"] == 0.6
        assert result["nozzle_temp"] == 210
        assert result["bed_temp"] == 55
        assert result["fan_speed"] == 100
        assert result["layer_height"] == 0.15
        assert result["extrusion_width"] == 0.68
        assert result["bed_center"] == "125,110"
        assert result["printer_model"] == "MK4S"

    def test_missing_keys_returns_partial(self, tmp_path) -> None:
        """Only present keys appear in the result dict."""
        ini = tmp_path / "config.ini"
        ini.write_text("temperature = 220\n")
        result = parse_prusaslicer_ini(str(ini))
        assert result == {"nozzle_temp": 220}

    def test_empty_file(self, tmp_path) -> None:
        ini = tmp_path / "config.ini"
        ini.write_text("")
        result = parse_prusaslicer_ini(str(ini))
        assert result == {}

    def test_semicolon_delimited_values(self, tmp_path) -> None:
        """Multi-extruder values use first value."""
        ini = tmp_path / "config.ini"
        ini.write_text(
            "nozzle_diameter = 0.4;0.6\n"
            "temperature = 215;220\n"
            "max_fan_speed = 80;100\n"
        )
        result = parse_prusaslicer_ini(str(ini))
        assert result["nozzle_diameter"] == 0.4
        assert result["nozzle_temp"] == 215
        assert result["fan_speed"] == 80

    def test_temperature_fallback_to_first_layer(self, tmp_path) -> None:
        """Uses first_layer_temperature when temperature is absent."""
        ini = tmp_path / "config.ini"
        ini.write_text("first_layer_temperature = 225\n")
        result = parse_prusaslicer_ini(str(ini))
        assert result["nozzle_temp"] == 225

    def test_temperature_preferred_over_first_layer(self, tmp_path) -> None:
        """temperature takes priority over first_layer_temperature."""
        ini = tmp_path / "config.ini"
        ini.write_text(
            "temperature = 210\n"
            "first_layer_temperature = 225\n"
        )
        result = parse_prusaslicer_ini(str(ini))
        assert result["nozzle_temp"] == 210

    def test_bed_temp_fallback(self, tmp_path) -> None:
        """Uses first_layer_bed_temperature as fallback."""
        ini = tmp_path / "config.ini"
        ini.write_text("first_layer_bed_temperature = 65\n")
        result = parse_prusaslicer_ini(str(ini))
        assert result["bed_temp"] == 65

    def test_bed_temp_preferred_over_first_layer(self, tmp_path) -> None:
        """bed_temperature takes priority."""
        ini = tmp_path / "config.ini"
        ini.write_text(
            "bed_temperature = 60\n"
            "first_layer_bed_temperature = 70\n"
        )
        result = parse_prusaslicer_ini(str(ini))
        assert result["bed_temp"] == 60

    def test_bed_temp_zero_is_valid(self, tmp_path) -> None:
        """Bed temp 0 (unheated) is valid."""
        ini = tmp_path / "config.ini"
        ini.write_text("bed_temperature = 0\n")
        result = parse_prusaslicer_ini(str(ini))
        assert result["bed_temp"] == 0

    def test_extrusion_width_auto_skipped(self, tmp_path) -> None:
        """extrusion_width = 0 means auto and is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("extrusion_width = 0\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "extrusion_width" not in result

    def test_extrusion_width_percentage_skipped(self, tmp_path) -> None:
        """Percentage-based extrusion width is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("extrusion_width = 105%\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "extrusion_width" not in result

    def test_invalid_nozzle_diameter_skipped(self, tmp_path) -> None:
        """Non-positive nozzle_diameter is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("nozzle_diameter = 0\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "nozzle_diameter" not in result

    def test_invalid_temperature_skipped(self, tmp_path) -> None:
        """Non-positive temperature is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("temperature = 0\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "nozzle_temp" not in result

    def test_fan_speed_out_of_range_skipped(self, tmp_path) -> None:
        """Fan speed outside 0-100 is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("max_fan_speed = 200\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "fan_speed" not in result

    def test_invalid_layer_height_skipped(self, tmp_path) -> None:
        """Non-positive layer_height is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("layer_height = 0\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "layer_height" not in result

    def test_empty_printer_model_skipped(self, tmp_path) -> None:
        """Empty printer_model string is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("printer_model = \n")
        result = parse_prusaslicer_ini(str(ini))
        assert "printer_model" not in result

    def test_malformed_bed_shape_skipped(self, tmp_path) -> None:
        """Malformed bed_shape is omitted."""
        ini = tmp_path / "config.ini"
        ini.write_text("bed_shape = garbage\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "bed_center" not in result

    def test_file_not_found_raises(self, tmp_path) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_prusaslicer_ini(str(tmp_path / "missing.ini"))

    def test_percentage_values_dont_break_parser(self, tmp_path) -> None:
        """PrusaSlicer values with % don't cause interpolation errors."""
        ini = tmp_path / "config.ini"
        ini.write_text(
            "fill_density = 15%\n"
            "temperature = 210\n"
        )
        result = parse_prusaslicer_ini(str(ini))
        assert result["nozzle_temp"] == 210

    def test_negative_nozzle_diameter_skipped(self, tmp_path) -> None:
        ini = tmp_path / "config.ini"
        ini.write_text("nozzle_diameter = -0.4\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "nozzle_diameter" not in result

    def test_non_numeric_temperature_skipped(self, tmp_path) -> None:
        ini = tmp_path / "config.ini"
        ini.write_text("temperature = abc\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "nozzle_temp" not in result

    def test_negative_layer_height_skipped(self, tmp_path) -> None:
        ini = tmp_path / "config.ini"
        ini.write_text("layer_height = -0.1\n")
        result = parse_prusaslicer_ini(str(ini))
        assert "layer_height" not in result
