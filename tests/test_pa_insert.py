"""Tests for filament_calibrator.pa_insert — pressure advance G-code insertion."""
from __future__ import annotations

import pytest

import gcode_lib as gl

from filament_calibrator.pa_insert import (
    PALevel,
    PAPatternRegion,
    _is_extrusion_move,
    _level_for_z,
    _region_for_x,
    compute_pa_levels,
    compute_pa_pattern_regions,
    insert_pa_commands,
    insert_pa_pattern_commands,
    pa_command,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lines(text: str):
    return gl.parse_lines(text)


def _raw_texts(lines):
    return [line.raw for line in lines]


# ---------------------------------------------------------------------------
# PALevel
# ---------------------------------------------------------------------------


class TestPALevel:
    def test_attributes(self):
        lv = PALevel(pa_value=0.05, z_start=1.0, z_end=2.0)
        assert lv.pa_value == 0.05
        assert lv.z_start == 1.0
        assert lv.z_end == 2.0


# ---------------------------------------------------------------------------
# pa_command
# ---------------------------------------------------------------------------


class TestPACommand:
    def test_default_coreone_uses_m572(self):
        result = pa_command(0.05)
        assert result == "M572 S0.0500 ; PA calibration level"

    def test_mini_uses_m900(self):
        result = pa_command(0.05, printer="MINI")
        assert result == "M900 K0.0500 ; PA calibration level"

    def test_mini_case_insensitive(self):
        result = pa_command(0.05, printer="mini")
        assert "M900 K0.0500" in result

    def test_four_decimal_places(self):
        result = pa_command(0.1)
        assert "S0.1000" in result

    def test_zero_value(self):
        result = pa_command(0.0)
        assert "S0.0000" in result

    def test_non_mini_printers_use_m572(self):
        for printer in ("COREONE", "MK4S", "MK3S"):
            result = pa_command(0.04, printer=printer)
            assert result.startswith("M572 S"), f"Expected M572 for {printer}"


# ---------------------------------------------------------------------------
# compute_pa_levels
# ---------------------------------------------------------------------------


class TestComputePALevels:
    def test_basic_levels(self):
        levels = compute_pa_levels(0.0, 0.05, 3, 1.0)
        assert len(levels) == 3
        assert levels[0].pa_value == pytest.approx(0.0)
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(1.0)
        assert levels[1].pa_value == pytest.approx(0.05)
        assert levels[2].pa_value == pytest.approx(0.1)
        assert levels[2].z_start == pytest.approx(2.0)
        assert levels[2].z_end == pytest.approx(3.0)

    def test_single_level(self):
        levels = compute_pa_levels(0.04, 0.01, 1, 2.0)
        assert len(levels) == 1
        assert levels[0].pa_value == pytest.approx(0.04)
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(2.0)

    def test_zero_levels(self):
        levels = compute_pa_levels(0.0, 0.05, 0, 1.0)
        assert levels == []

    def test_custom_level_height(self):
        levels = compute_pa_levels(0.0, 0.01, 3, 2.0)
        assert levels[0].z_end == pytest.approx(2.0)
        assert levels[1].z_start == pytest.approx(2.0)
        assert levels[2].z_start == pytest.approx(4.0)

    def test_rounding_prevents_drift(self):
        """PA values are rounded to 4 decimals to prevent float drift."""
        levels = compute_pa_levels(0.0, 0.1, 10, 1.0)
        # Without rounding, 0.1 * 3 = 0.30000000000000004
        assert levels[3].pa_value == pytest.approx(0.3)
        assert levels[9].pa_value == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# _level_for_z
# ---------------------------------------------------------------------------


class TestLevelForZ:
    def test_in_first_level(self):
        levels = compute_pa_levels(0.0, 0.05, 3, 1.0)
        assert _level_for_z(0.5, levels).pa_value == pytest.approx(0.0)

    def test_in_second_level(self):
        levels = compute_pa_levels(0.0, 0.05, 3, 1.0)
        assert _level_for_z(1.5, levels).pa_value == pytest.approx(0.05)

    def test_at_boundary(self):
        levels = compute_pa_levels(0.0, 0.05, 3, 1.0)
        # z_end is inclusive — boundary layer belongs to current level
        assert _level_for_z(1.0, levels).pa_value == pytest.approx(0.0)

    def test_below_range(self):
        # Levels start at z=0, so nothing is below
        levels = compute_pa_levels(0.0, 0.05, 3, 1.0)
        assert _level_for_z(-0.5, levels) is None

    def test_above_range(self):
        levels = compute_pa_levels(0.0, 0.05, 3, 1.0)
        assert _level_for_z(3.5, levels) is None

    def test_empty_levels(self):
        assert _level_for_z(0.5, []) is None


# ---------------------------------------------------------------------------
# insert_pa_commands
# ---------------------------------------------------------------------------


class TestInsertPACommands:
    def test_basic_insertion_default_m572(self):
        """M572 commands are inserted at level boundaries (default printer)."""
        gcode = (
            "G28\n"
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z1.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_pa_levels(0.0, 0.05, 2, 1.0)
        result = insert_pa_commands(lines, levels)
        texts = _raw_texts(result)

        m572_lines = [t for t in texts if t.startswith("M572")]
        assert len(m572_lines) == 2
        assert "S0.0000" in m572_lines[0]
        assert "S0.0500" in m572_lines[1]

    def test_mini_uses_m900(self):
        """MINI printer inserts M900 commands."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
        )
        lines = _lines(gcode)
        levels = compute_pa_levels(0.0, 0.05, 1, 1.0)
        result = insert_pa_commands(lines, levels, printer="MINI")
        texts = _raw_texts(result)

        m900_lines = [t for t in texts if t.startswith("M900")]
        assert len(m900_lines) == 1
        assert "K0.0000" in m900_lines[0]

    def test_no_duplicate_commands(self):
        """Same-level layers don't get duplicate PA commands."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z0.4 F1000\n"
            "G1 X20 E2\n"
            "G1 Z0.6 F1000\n"
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        levels = compute_pa_levels(0.0, 0.05, 1, 1.0)
        result = insert_pa_commands(lines, levels)
        texts = _raw_texts(result)

        pa_lines = [t for t in texts if t.startswith("M572")]
        assert len(pa_lines) == 1

    def test_empty_levels_no_modification(self):
        gcode = "G28\nG1 X10 E1\n"
        lines = _lines(gcode)
        result = insert_pa_commands(lines, [])
        assert len(result) == len(lines)

    def test_empty_lines(self):
        result = insert_pa_commands([], compute_pa_levels(0.0, 0.05, 3, 1.0))
        assert result == []

    def test_above_last_level_keeps_pa(self):
        """Layers above the last level don't generate new PA commands."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z100.0 F1000\n"
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        levels = compute_pa_levels(0.0, 0.05, 1, 1.0)  # single level: z=0-1
        result = insert_pa_commands(lines, levels)
        texts = _raw_texts(result)

        pa_lines = [t for t in texts if t.startswith("M572")]
        assert len(pa_lines) == 1
        assert "S0.0000" in pa_lines[0]

    def test_command_order_in_output(self):
        """PA command appears before the first line of the new-level layer."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z1.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_pa_levels(0.0, 0.05, 2, 1.0)
        result = insert_pa_commands(lines, levels)
        texts = _raw_texts(result)

        idx_pa_0 = next((i for i, t in enumerate(texts) if "S0.0000" in t), -1)
        idx_z0_2 = next((i for i, t in enumerate(texts) if "Z0.2" in t), -1)
        assert idx_pa_0 != -1
        assert idx_z0_2 != -1
        assert idx_pa_0 < idx_z0_2

        idx_pa_1 = next((i for i, t in enumerate(texts) if "S0.0500" in t), -1)
        idx_z1_2 = next((i for i, t in enumerate(texts) if "Z1.2" in t), -1)
        assert idx_pa_1 != -1
        assert idx_z1_2 != -1
        assert idx_pa_1 < idx_z1_2

    def test_immutable_input(self):
        """Original list is not mutated."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
        )
        lines = _lines(gcode)
        original_len = len(lines)
        levels = compute_pa_levels(0.0, 0.05, 1, 1.0)
        insert_pa_commands(lines, levels)
        assert len(lines) == original_len


# ===========================================================================
# X-based PA insertion (pattern method)
# ===========================================================================


# ---------------------------------------------------------------------------
# PAPatternRegion
# ---------------------------------------------------------------------------


class TestPAPatternRegion:
    def test_attributes(self):
        r = PAPatternRegion(pa_value=0.05, x_start=10.0, x_end=20.0)
        assert r.pa_value == 0.05
        assert r.x_start == 10.0
        assert r.x_end == 20.0


# ---------------------------------------------------------------------------
# compute_pa_pattern_regions
# ---------------------------------------------------------------------------


class TestComputePaPatternRegions:
    def test_empty_inputs(self):
        assert compute_pa_pattern_regions([], []) == []

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="same length"):
            compute_pa_pattern_regions([0.0, 0.1], [100.0])

    def test_single_region(self):
        regions = compute_pa_pattern_regions([0.05], [100.0])
        assert len(regions) == 1
        assert regions[0].pa_value == 0.05
        assert regions[0].x_start == float("-inf")
        assert regions[0].x_end == float("inf")

    def test_two_regions(self):
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        assert len(regions) == 2
        assert regions[0].x_start == float("-inf")
        assert regions[0].x_end == pytest.approx(125.0)
        assert regions[1].x_start == pytest.approx(125.0)
        assert regions[1].x_end == float("inf")

    def test_three_regions_boundaries(self):
        regions = compute_pa_pattern_regions(
            [0.0, 0.05, 0.1], [80.0, 120.0, 160.0],
        )
        assert len(regions) == 3
        assert regions[0].x_start == float("-inf")
        assert regions[0].x_end == pytest.approx(100.0)
        assert regions[1].x_start == pytest.approx(100.0)
        assert regions[1].x_end == pytest.approx(140.0)
        assert regions[2].x_start == pytest.approx(140.0)
        assert regions[2].x_end == float("inf")

    def test_pa_values_assigned(self):
        regions = compute_pa_pattern_regions(
            [0.01, 0.02, 0.03], [50.0, 100.0, 150.0],
        )
        assert regions[0].pa_value == 0.01
        assert regions[1].pa_value == 0.02
        assert regions[2].pa_value == 0.03


# ---------------------------------------------------------------------------
# _region_for_x
# ---------------------------------------------------------------------------


class TestRegionForX:
    def test_in_first_region(self):
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        assert _region_for_x(90.0, regions).pa_value == 0.0

    def test_in_second_region(self):
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        assert _region_for_x(130.0, regions).pa_value == 0.1

    def test_at_boundary_goes_to_next(self):
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        # x_start is inclusive, so the boundary point belongs to region 1
        assert _region_for_x(125.0, regions).pa_value == 0.1

    def test_far_left(self):
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        assert _region_for_x(-1000.0, regions).pa_value == 0.0

    def test_far_right(self):
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        assert _region_for_x(9999.0, regions).pa_value == 0.1

    def test_empty_regions(self):
        assert _region_for_x(50.0, []) is None


# ---------------------------------------------------------------------------
# _is_extrusion_move
# ---------------------------------------------------------------------------


class TestIsExtrusionMove:
    def test_g1_with_x_and_e(self):
        line = gl.parse_line("G1 X10 E1.5")
        assert _is_extrusion_move(line) is True

    def test_g1_with_y_and_e(self):
        line = gl.parse_line("G1 Y20 E1.5")
        assert _is_extrusion_move(line) is True

    def test_g1_with_x_y_and_e(self):
        line = gl.parse_line("G1 X10 Y20 E1.5")
        assert _is_extrusion_move(line) is True

    def test_g1_without_e(self):
        """Travel move (no extrusion) should return False."""
        line = gl.parse_line("G1 X10 Y20")
        assert _is_extrusion_move(line) is False

    def test_g1_e_only_retraction(self):
        """Retraction (E only, no X/Y) should return False."""
        line = gl.parse_line("G1 E-1.0")
        assert _is_extrusion_move(line) is False

    def test_g1_z_and_e(self):
        """Z-only move with E (no X/Y) should return False."""
        line = gl.parse_line("G1 Z0.2 E0.5")
        assert _is_extrusion_move(line) is False

    def test_g0_travel_move(self):
        """G0 is never an extrusion move."""
        line = gl.parse_line("G0 X10 E1")
        assert _is_extrusion_move(line) is False

    def test_non_move_command(self):
        line = gl.parse_line("M104 S200")
        assert _is_extrusion_move(line) is False


# ---------------------------------------------------------------------------
# insert_pa_pattern_commands
# ---------------------------------------------------------------------------


class TestInsertPaPatternCommands:
    def test_basic_insertion_default_m572(self):
        """M572 commands are inserted when toolpath enters new X region."""
        gcode = (
            "G28\n"
            "G1 Z0.2 F1000\n"
            "G1 X90 E1\n"
            "G1 X130 E2\n"
        )
        lines = _lines(gcode)
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        result = insert_pa_pattern_commands(lines, regions)
        texts = _raw_texts(result)

        m572_lines = [t for t in texts if t.startswith("M572")]
        assert len(m572_lines) == 2
        assert "S0.0000" in m572_lines[0]
        assert "S0.1000" in m572_lines[1]

    def test_mini_uses_m900(self):
        """MINI printer inserts M900 commands for pattern method."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X90 E1\n"
            "G1 X130 E2\n"
        )
        lines = _lines(gcode)
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        result = insert_pa_pattern_commands(lines, regions, printer="MINI")
        texts = _raw_texts(result)

        m900_lines = [t for t in texts if t.startswith("M900")]
        assert len(m900_lines) == 2
        assert "K0.0000" in m900_lines[0]
        assert "K0.1000" in m900_lines[1]

    def test_no_duplicate_in_same_region(self):
        """Multiple moves within the same X region don't produce duplicates."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X90 E1\n"
            "G1 X95 E2\n"
            "G1 X92 E3\n"
        )
        lines = _lines(gcode)
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        result = insert_pa_pattern_commands(lines, regions)
        texts = _raw_texts(result)

        pa_lines = [t for t in texts if t.startswith("M572")]
        assert len(pa_lines) == 1

    def test_empty_regions_no_modification(self):
        gcode = "G28\nG1 X10 E1\n"
        lines = _lines(gcode)
        result = insert_pa_pattern_commands(lines, [])
        assert len(result) == len(lines)

    def test_empty_lines(self):
        regions = compute_pa_pattern_regions([0.0], [100.0])
        result = insert_pa_pattern_commands([], regions)
        assert result == []

    def test_command_before_extrusion_move(self):
        """PA command appears before the extrusion move that triggers it."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X90 E1\n"
            "G1 X130 E2\n"
        )
        lines = _lines(gcode)
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        result = insert_pa_pattern_commands(lines, regions)
        texts = _raw_texts(result)

        idx_pa1 = next(i for i, t in enumerate(texts) if "S0.1000" in t)
        idx_x130 = next(i for i, t in enumerate(texts) if "X130" in t)
        assert idx_pa1 < idx_x130

    def test_travel_moves_dont_trigger(self):
        """Travel moves (no E) don't trigger PA changes."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X90 E1\n"
            "G1 X130\n"
            "G1 X90 E2\n"
        )
        lines = _lines(gcode)
        regions = compute_pa_pattern_regions([0.0, 0.1], [100.0, 150.0])
        result = insert_pa_pattern_commands(lines, regions)
        texts = _raw_texts(result)

        pa_lines = [t for t in texts if t.startswith("M572")]
        # First extrusion at X90 → region 0, travel to X130 (no PA change),
        # extrusion back at X90 → still region 0 (no change needed)
        assert len(pa_lines) == 1

    def test_immutable_input(self):
        """Original list is not mutated."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X90 E1\n"
        )
        lines = _lines(gcode)
        original_len = len(lines)
        regions = compute_pa_pattern_regions([0.0], [100.0])
        insert_pa_pattern_commands(lines, regions)
        assert len(lines) == original_len
