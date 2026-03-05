"""Tests for filament_calibrator.printer_gcode — printer G-code templates."""
from __future__ import annotations

import pytest

from filament_calibrator.printer_gcode import (
    KNOWN_PRINTERS,
    MBL_TEMP,
    PrinterGCode,
    _PRINTER_ALIASES,
    _TEMPLATES,
    compute_bed_center,
    compute_bed_shape,
    compute_m555,
    render_end_gcode,
    render_start_gcode,
    resolve_printer,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestKnownPrinters:
    def test_is_tuple(self):
        assert isinstance(KNOWN_PRINTERS, tuple)

    def test_contains_expected_printers(self):
        for p in ("COREONE", "COREONEL", "MK4S", "MINI", "XL"):
            assert p in KNOWN_PRINTERS

    def test_all_have_templates(self):
        for p in KNOWN_PRINTERS:
            assert p in _TEMPLATES


class TestPrinterAliases:
    def test_mk4_maps_to_mk4s(self):
        assert _PRINTER_ALIASES["MK4"] == "MK4S"


class TestMBLTemp:
    def test_value(self):
        assert MBL_TEMP == 170


# ---------------------------------------------------------------------------
# resolve_printer
# ---------------------------------------------------------------------------


class TestResolvePrinter:
    def test_exact_name(self):
        assert resolve_printer("COREONE") == "COREONE"

    def test_case_insensitive(self):
        assert resolve_printer("coreone") == "COREONE"
        assert resolve_printer("CoreOne") == "COREONE"

    def test_alias_mk4(self):
        assert resolve_printer("mk4") == "MK4S"
        assert resolve_printer("MK4") == "MK4S"

    def test_all_known_printers(self):
        for p in KNOWN_PRINTERS:
            assert resolve_printer(p) == p

    def test_unknown_exits(self):
        with pytest.raises(SystemExit):
            resolve_printer("UNKNOWN_PRINTER")


# ---------------------------------------------------------------------------
# compute_bed_center
# ---------------------------------------------------------------------------


class TestComputeBedCenter:
    def test_coreone(self):
        # 250x220 bed → 125,110
        assert compute_bed_center("COREONE") == "125,110"

    def test_coreonel(self):
        # 300x300 bed → 150,150
        assert compute_bed_center("COREONEL") == "150,150"

    def test_mk4s(self):
        # MK4S uses MK4 preset: 250x210 → 125,105
        assert compute_bed_center("MK4S") == "125,105"

    def test_mini(self):
        # 180x180 bed → 90,90
        assert compute_bed_center("MINI") == "90,90"

    def test_xl(self):
        # 360x360 bed → 180,180
        assert compute_bed_center("XL") == "180,180"

    def test_unknown_returns_default(self):
        assert compute_bed_center("NONEXISTENT") == "125,110"


# ---------------------------------------------------------------------------
# compute_bed_shape
# ---------------------------------------------------------------------------


class TestComputeBedShape:
    def test_coreone(self):
        assert compute_bed_shape("COREONE") == "0x0,250x0,250x220,0x220"

    def test_mk4s(self):
        # MK4S → MK4 preset: 250x210
        assert compute_bed_shape("MK4S") == "0x0,250x0,250x210,0x210"

    def test_unknown_returns_default(self):
        assert compute_bed_shape("NONEXISTENT") == "0x0,250x0,250x220,0x220"


# ---------------------------------------------------------------------------
# compute_m555
# ---------------------------------------------------------------------------


class TestComputeM555:
    def test_centered_model(self):
        result = compute_m555("125,110", 60.0, 60.0)
        assert result == {
            "m555_x": 95,
            "m555_y": 80,
            "m555_w": 60,
            "m555_h": 60,
        }

    def test_mini_bed(self):
        result = compute_m555("90,90", 60.0, 60.0)
        assert result == {
            "m555_x": 60,
            "m555_y": 60,
            "m555_w": 60,
            "m555_h": 60,
        }


# ---------------------------------------------------------------------------
# render_start_gcode
# ---------------------------------------------------------------------------


class TestRenderStartGcode:
    def test_coreone_contains_printer_check(self):
        result = render_start_gcode(
            "COREONE",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="125,110",
            model_width=60.0,
            model_depth=60.0,
        )
        assert 'M862.3 P "COREONE"' in result

    def test_coreone_contains_temps(self):
        result = render_start_gcode(
            "COREONE",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="125,110",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "M140 S60" in result
        assert "M109 S215" in result

    def test_nozzle_dia(self):
        result = render_start_gcode(
            "COREONE",
            nozzle_dia=0.6,
            bed_temp=60,
            hotend_temp=215,
            bed_center="125,110",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "M862.1 P0.6" in result

    def test_mbl_temp_capped(self):
        result = render_start_gcode(
            "COREONE",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="125,110",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "M109 R170" in result

    def test_mbl_temp_low_hotend(self):
        """When hotend_temp < MBL_TEMP, mbl_temp = hotend_temp."""
        result = render_start_gcode(
            "MINI",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=160,
            bed_center="90,90",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "M109 R160" in result

    def test_cool_fan_enabled(self):
        result = render_start_gcode(
            "COREONE",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="125,110",
            model_width=60.0,
            model_depth=60.0,
            cool_fan=True,
        )
        assert "M106 S255" in result

    def test_cool_fan_disabled(self):
        result = render_start_gcode(
            "COREONE",
            nozzle_dia=0.4,
            bed_temp=110,
            hotend_temp=260,
            bed_center="125,110",
            model_width=60.0,
            model_depth=60.0,
            cool_fan=False,
        )
        assert "M106 S255" not in result

    def test_m555_values(self):
        result = render_start_gcode(
            "COREONE",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="125,110",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "M555 X95 Y80 W60 H60" in result

    def test_all_printers_render(self):
        """All known printers render start gcode without errors."""
        for printer in KNOWN_PRINTERS:
            center = compute_bed_center(printer)
            result = render_start_gcode(
                printer,
                nozzle_dia=0.4,
                bed_temp=60,
                hotend_temp=215,
                bed_center=center,
                model_width=60.0,
                model_depth=60.0,
            )
            assert len(result) > 100
            assert "{" not in result  # no unrendered placeholders

    def test_coreonel_has_bed_fans(self):
        result = render_start_gcode(
            "COREONEL",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="150,150",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "M106 P5 R A125 B10" in result

    def test_xl_has_dual_home(self):
        result = render_start_gcode(
            "XL",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="180,180",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "G28 XY" in result
        assert "G28 Z" in result

    def test_mini_has_intro_line(self):
        result = render_start_gcode(
            "MINI",
            nozzle_dia=0.4,
            bed_temp=60,
            hotend_temp=215,
            bed_center="90,90",
            model_width=60.0,
            model_depth=60.0,
        )
        assert "Intro line" in result


# ---------------------------------------------------------------------------
# render_end_gcode
# ---------------------------------------------------------------------------


class TestRenderEndGcode:
    def test_coreone_contains_park(self):
        result = render_end_gcode("COREONE", max_layer_z=10.0)
        assert "G1 X242 Y211" in result

    def test_park_z_offset(self):
        result = render_end_gcode("COREONE", max_layer_z=10.0)
        # park_z = 10.0 + 10.0 = 20.0
        assert "Z20.0 F720" in result

    def test_park_z_capped_at_max(self):
        # COREONE max_z = 250. park_z = min(245+10, 250) = 250.0
        result = render_end_gcode("COREONE", max_layer_z=245.0)
        assert "Z250.0 F720" in result

    def test_max_layer_z_comment(self):
        result = render_end_gcode("COREONE", max_layer_z=10.0)
        assert "max_layer_z = 10.00" in result

    def test_resets_linear_advance(self):
        result = render_end_gcode("COREONE", max_layer_z=10.0)
        assert "M900 K0" in result

    def test_all_printers_render(self):
        """All known printers render end gcode without errors."""
        for printer in KNOWN_PRINTERS:
            result = render_end_gcode(printer, max_layer_z=5.0)
            assert len(result) > 50
            assert "{" not in result  # no unrendered placeholders

    def test_coreonel_turns_off_bed_fans(self):
        result = render_end_gcode("COREONEL", max_layer_z=10.0)
        assert "M107 P5" in result

    def test_mk4s_disables_input_shaping(self):
        result = render_end_gcode("MK4S", max_layer_z=10.0)
        assert "M593 X T2 F0" in result
        assert "M593 Y T2 F0" in result

    def test_xl_park_position(self):
        result = render_end_gcode("XL", max_layer_z=10.0)
        assert "G1 X6 Y350" in result

    def test_mini_park_position(self):
        result = render_end_gcode("MINI", max_layer_z=10.0)
        assert "G1 X90 Y170" in result


# ---------------------------------------------------------------------------
# PrinterGCode
# ---------------------------------------------------------------------------


class TestPrinterGCode:
    def test_dataclass(self):
        pgc = PrinterGCode(start="start", end="end")
        assert pgc.start == "start"
        assert pgc.end == "end"

    def test_all_templates_are_printergcode(self):
        for name, pgc in _TEMPLATES.items():
            assert isinstance(pgc, PrinterGCode), f"{name} is not PrinterGCode"
