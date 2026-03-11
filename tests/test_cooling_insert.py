"""Tests for filament_calibrator.cooling_insert — fan-speed G-code insertion."""
from __future__ import annotations

import pytest

import gcode_lib as gl

from filament_calibrator.cooling_insert import (
    CoolingLevel,
    _level_for_z,
    compute_cooling_levels,
    fan_command,
    insert_cooling_commands,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lines(text: str):
    return gl.parse_lines(text)


def _raw_texts(lines):
    return [line.raw for line in lines]


# ---------------------------------------------------------------------------
# CoolingLevel
# ---------------------------------------------------------------------------


class TestCoolingLevel:
    def test_attributes(self):
        lv = CoolingLevel(fan_percent=50, z_start=1.0, z_end=2.0)
        assert lv.fan_percent == 50
        assert lv.z_start == 1.0
        assert lv.z_end == 2.0


# ---------------------------------------------------------------------------
# fan_command
# ---------------------------------------------------------------------------


class TestFanCommand:
    def test_m106_format(self):
        result = fan_command(50)
        assert result == "M106 S128 ; cooling calibration level"

    def test_zero_percent(self):
        result = fan_command(0)
        assert "S0" in result

    def test_fifty_percent(self):
        result = fan_command(50)
        assert "S128" in result

    def test_hundred_percent(self):
        result = fan_command(100)
        assert "S255" in result

    def test_boundary_low(self):
        result = fan_command(1)
        # 1 * 255 / 100 = 2.55, rounds to 3
        assert "S3" in result

    def test_boundary_high(self):
        result = fan_command(99)
        # 99 * 255 / 100 = 252.45, rounds to 252
        assert "S252" in result


# ---------------------------------------------------------------------------
# compute_cooling_levels
# ---------------------------------------------------------------------------


class TestComputeCoolingLevels:
    def test_basic_levels(self):
        levels = compute_cooling_levels(0, 10, 3, 5.0)
        assert len(levels) == 3
        assert levels[0].fan_percent == 0
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(5.0)
        assert levels[1].fan_percent == 10
        assert levels[2].fan_percent == 20
        assert levels[2].z_start == pytest.approx(10.0)
        assert levels[2].z_end == pytest.approx(15.0)

    def test_with_base_height(self):
        levels = compute_cooling_levels(0, 10, 3, 5.0, base_height=1.0)
        assert levels[0].z_start == pytest.approx(1.0)
        assert levels[0].z_end == pytest.approx(6.0)
        assert levels[1].z_start == pytest.approx(6.0)
        assert levels[2].z_end == pytest.approx(16.0)

    def test_single_level(self):
        levels = compute_cooling_levels(50, 10, 1, 5.0)
        assert len(levels) == 1
        assert levels[0].fan_percent == 50
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(5.0)

    def test_zero_levels(self):
        levels = compute_cooling_levels(0, 10, 0, 5.0)
        assert levels == []

    def test_custom_height(self):
        levels = compute_cooling_levels(0, 10, 3, 10.0)
        assert levels[0].z_end == pytest.approx(10.0)
        assert levels[1].z_start == pytest.approx(10.0)
        assert levels[2].z_start == pytest.approx(20.0)

    def test_rounding_prevents_drift(self):
        """Fan percentages are rounded to prevent float drift."""
        levels = compute_cooling_levels(0, 10, 11, 5.0)
        assert levels[3].fan_percent == 30
        assert levels[10].fan_percent == 100


# ---------------------------------------------------------------------------
# _level_for_z
# ---------------------------------------------------------------------------


class TestLevelForZ:
    def test_in_first_level(self):
        levels = compute_cooling_levels(0, 10, 3, 5.0, base_height=1.0)
        assert _level_for_z(3.0, levels).fan_percent == 0

    def test_in_second_level(self):
        levels = compute_cooling_levels(0, 10, 3, 5.0, base_height=1.0)
        assert _level_for_z(7.0, levels).fan_percent == 10

    def test_at_boundary(self):
        levels = compute_cooling_levels(0, 10, 3, 5.0, base_height=1.0)
        # z_start is inclusive
        assert _level_for_z(6.0, levels).fan_percent == 10

    def test_below_range(self):
        levels = compute_cooling_levels(0, 10, 3, 5.0, base_height=1.0)
        assert _level_for_z(0.5, levels) is None

    def test_above_range(self):
        levels = compute_cooling_levels(0, 10, 3, 5.0, base_height=1.0)
        assert _level_for_z(20.0, levels) is None

    def test_empty_levels(self):
        assert _level_for_z(0.5, []) is None


# ---------------------------------------------------------------------------
# insert_cooling_commands
# ---------------------------------------------------------------------------


class TestInsertCoolingCommands:
    def test_basic_insertion(self):
        """M106 commands are inserted at level boundaries."""
        gcode = (
            "G28\n"
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z6.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_cooling_levels(0, 50, 2, 5.0, base_height=1.0)
        result = insert_cooling_commands(lines, levels)
        texts = _raw_texts(result)

        m106_lines = [t for t in texts if t.startswith("M106")]
        assert len(m106_lines) == 2
        assert "S0" in m106_lines[0]
        assert "S128" in m106_lines[1]

    def test_base_plate_gets_first_level_fan(self):
        """Layers below the first level's z_start get first level's fan speed."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z0.4 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_cooling_levels(50, 10, 2, 5.0, base_height=1.0)
        result = insert_cooling_commands(lines, levels)
        texts = _raw_texts(result)

        m106_lines = [t for t in texts if t.startswith("M106")]
        assert len(m106_lines) == 1
        assert "S128" in m106_lines[0]

    def test_no_duplicate_commands(self):
        """Same-level layers don't get duplicate M106 commands."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z1.4 F1000\n"
            "G1 X20 E2\n"
            "G1 Z1.6 F1000\n"
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        levels = compute_cooling_levels(0, 50, 1, 5.0, base_height=1.0)
        result = insert_cooling_commands(lines, levels)
        texts = _raw_texts(result)

        m106_lines = [t for t in texts if t.startswith("M106")]
        assert len(m106_lines) == 1

    def test_empty_levels_no_modification(self):
        gcode = "G28\nG1 X10 E1\n"
        lines = _lines(gcode)
        result = insert_cooling_commands(lines, [])
        assert len(result) == len(lines)

    def test_empty_lines(self):
        result = insert_cooling_commands(
            [], compute_cooling_levels(0, 10, 3, 5.0),
        )
        assert result == []

    def test_above_last_level_keeps_fan(self):
        """Layers above the last level don't generate new M106 commands."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z100.0 F1000\n"
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        levels = compute_cooling_levels(50, 10, 1, 5.0, base_height=1.0)
        result = insert_cooling_commands(lines, levels)
        texts = _raw_texts(result)

        m106_lines = [t for t in texts if t.startswith("M106")]
        assert len(m106_lines) == 1
        assert "S128" in m106_lines[0]

    def test_command_order_in_output(self):
        """M106 command appears before the first line of the new-level layer."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z6.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_cooling_levels(0, 50, 2, 5.0, base_height=1.0)
        result = insert_cooling_commands(lines, levels)
        texts = _raw_texts(result)

        idx_m106_0 = next(
            (i for i, t in enumerate(texts) if "S0 " in t), -1,
        )
        idx_z1_2 = next(
            (i for i, t in enumerate(texts) if "Z1.2" in t), -1,
        )
        assert idx_m106_0 != -1
        assert idx_z1_2 != -1
        assert idx_m106_0 < idx_z1_2

        idx_m106_1 = next(
            (i for i, t in enumerate(texts) if "S128" in t), -1,
        )
        idx_z6_2 = next(
            (i for i, t in enumerate(texts) if "Z6.2" in t), -1,
        )
        assert idx_m106_1 != -1
        assert idx_z6_2 != -1
        assert idx_m106_1 < idx_z6_2

    def test_immutable_input(self):
        """Original list is not mutated."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
        )
        lines = _lines(gcode)
        original_len = len(lines)
        levels = compute_cooling_levels(0, 50, 1, 5.0, base_height=1.0)
        insert_cooling_commands(lines, levels)
        assert len(lines) == original_len
