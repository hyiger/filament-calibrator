"""Tests for filament_calibrator.retraction_speed_insert — retraction speed G-code insertion."""
from __future__ import annotations

import pytest

from tests.helpers import parse_gcode as _lines, raw_texts as _raw_texts

from filament_calibrator.retraction_speed_insert import (
    RetractionSpeedLevel,
    _level_for_z,
    compute_retraction_speed_levels,
    insert_retraction_speed_commands,
    retraction_speed_command,
)


# ---------------------------------------------------------------------------
# RetractionSpeedLevel
# ---------------------------------------------------------------------------


class TestRetractionSpeedLevel:
    def test_attributes(self):
        lv = RetractionSpeedLevel(speed_mm_s=30.0, z_start=1.0, z_end=2.0)
        assert lv.speed_mm_s == 30.0
        assert lv.z_start == 1.0
        assert lv.z_end == 2.0


# ---------------------------------------------------------------------------
# retraction_speed_command
# ---------------------------------------------------------------------------


class TestRetractionSpeedCommand:
    def test_m207_format(self):
        result = retraction_speed_command(0.8, 30.0)
        assert result == "M207 S0.80 F1800 ; retraction speed calibration level"

    def test_speed_conversion(self):
        """30 mm/s should become F1800 (30 * 60 = 1800 mm/min)."""
        result = retraction_speed_command(0.8, 30.0)
        assert "F1800" in result

    def test_formatting_length(self):
        result = retraction_speed_command(1.0, 20.0)
        assert "S1.00" in result
        assert "F1200" in result

    def test_small_speed(self):
        result = retraction_speed_command(0.5, 10.0)
        assert "S0.50" in result
        assert "F600" in result

    def test_zero_length(self):
        result = retraction_speed_command(0.0, 40.0)
        assert "S0.00" in result
        assert "F2400" in result


# ---------------------------------------------------------------------------
# compute_retraction_speed_levels
# ---------------------------------------------------------------------------


class TestComputeRetractionSpeedLevels:
    def test_basic_levels(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 1.0)
        assert len(levels) == 3
        assert levels[0].speed_mm_s == pytest.approx(20.0)
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(1.0)
        assert levels[1].speed_mm_s == pytest.approx(25.0)
        assert levels[2].speed_mm_s == pytest.approx(30.0)
        assert levels[2].z_start == pytest.approx(2.0)
        assert levels[2].z_end == pytest.approx(3.0)

    def test_with_base_height(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 1.0, base_height=1.0)
        assert levels[0].z_start == pytest.approx(1.0)
        assert levels[0].z_end == pytest.approx(2.0)
        assert levels[1].z_start == pytest.approx(2.0)
        assert levels[2].z_end == pytest.approx(4.0)

    def test_single_level(self):
        levels = compute_retraction_speed_levels(30.0, 5.0, 1, 2.0)
        assert len(levels) == 1
        assert levels[0].speed_mm_s == pytest.approx(30.0)
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(2.0)

    def test_zero_levels(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 0, 1.0)
        assert levels == []

    def test_custom_level_height(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 2.0)
        assert levels[0].z_end == pytest.approx(2.0)
        assert levels[1].z_start == pytest.approx(2.0)
        assert levels[2].z_start == pytest.approx(4.0)

    def test_rounding_prevents_drift(self):
        """Retraction speeds are rounded to prevent float drift."""
        levels = compute_retraction_speed_levels(20.0, 0.1, 10, 1.0)
        # Without rounding, 0.1 * 3 = 0.30000000000000004
        assert levels[3].speed_mm_s == pytest.approx(20.3)
        assert levels[9].speed_mm_s == pytest.approx(20.9)


# ---------------------------------------------------------------------------
# _level_for_z
# ---------------------------------------------------------------------------


class TestLevelForZ:
    def test_in_first_level(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 1.0, base_height=1.0)
        assert _level_for_z(1.5, levels).speed_mm_s == pytest.approx(20.0)

    def test_in_second_level(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 1.0, base_height=1.0)
        assert _level_for_z(2.5, levels).speed_mm_s == pytest.approx(25.0)

    def test_at_boundary(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 1.0, base_height=1.0)
        # z_end is inclusive — boundary layer belongs to current level
        assert _level_for_z(2.0, levels).speed_mm_s == pytest.approx(20.0)

    def test_below_range(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 1.0, base_height=1.0)
        assert _level_for_z(0.5, levels) is None

    def test_above_range(self):
        levels = compute_retraction_speed_levels(20.0, 5.0, 3, 1.0, base_height=1.0)
        assert _level_for_z(4.5, levels) is None

    def test_empty_levels(self):
        assert _level_for_z(0.5, []) is None


# ---------------------------------------------------------------------------
# insert_retraction_speed_commands
# ---------------------------------------------------------------------------


class TestInsertRetractionSpeedCommands:
    def test_basic_insertion(self):
        """M207 commands are inserted at level boundaries with both S and F."""
        gcode = (
            "G28\n"
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z2.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_retraction_speed_levels(20.0, 10.0, 2, 1.0, base_height=1.0)
        result = insert_retraction_speed_commands(lines, levels, 0.8)
        texts = _raw_texts(result)

        m207_lines = [t for t in texts if t.startswith("M207")]
        assert len(m207_lines) == 2
        # First level: 20 mm/s → F1200, S0.80
        assert "S0.80" in m207_lines[0]
        assert "F1200" in m207_lines[0]
        # Second level: 30 mm/s → F1800, S0.80
        assert "S0.80" in m207_lines[1]
        assert "F1800" in m207_lines[1]

    def test_base_plate_gets_first_level(self):
        """Layers below the first level's z_start get first level's speed."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z0.4 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_retraction_speed_levels(25.0, 5.0, 2, 1.0, base_height=1.0)
        result = insert_retraction_speed_commands(lines, levels, 0.8)
        texts = _raw_texts(result)

        m207_lines = [t for t in texts if t.startswith("M207")]
        assert len(m207_lines) == 1
        # Should use first level's speed: 25 mm/s → F1500
        assert "F1500" in m207_lines[0]
        assert "S0.80" in m207_lines[0]

    def test_no_duplicate_commands(self):
        """Same-level layers don't get duplicate M207 commands."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z1.4 F1000\n"
            "G1 X20 E2\n"
            "G1 Z1.6 F1000\n"
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        levels = compute_retraction_speed_levels(20.0, 5.0, 1, 1.0, base_height=1.0)
        result = insert_retraction_speed_commands(lines, levels, 0.8)
        texts = _raw_texts(result)

        m207_lines = [t for t in texts if t.startswith("M207")]
        assert len(m207_lines) == 1

    def test_empty_levels_no_modification(self):
        gcode = "G28\nG1 X10 E1\n"
        lines = _lines(gcode)
        result = insert_retraction_speed_commands(lines, [], 0.8)
        assert len(result) == len(lines)

    def test_empty_lines(self):
        result = insert_retraction_speed_commands(
            [], compute_retraction_speed_levels(20.0, 5.0, 3, 1.0), 0.8,
        )
        assert result == []

    def test_above_last_level_keeps_speed(self):
        """Layers above the last level don't generate new M207 commands."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z100.0 F1000\n"
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        levels = compute_retraction_speed_levels(20.0, 5.0, 1, 1.0, base_height=1.0)
        result = insert_retraction_speed_commands(lines, levels, 0.8)
        texts = _raw_texts(result)

        m207_lines = [t for t in texts if t.startswith("M207")]
        assert len(m207_lines) == 1
        assert "F1200" in m207_lines[0]

    def test_command_order_in_output(self):
        """M207 command appears before the first line of the new-level layer."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z2.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        levels = compute_retraction_speed_levels(20.0, 10.0, 2, 1.0, base_height=1.0)
        result = insert_retraction_speed_commands(lines, levels, 0.8)
        texts = _raw_texts(result)

        idx_m207_0 = next(
            (i for i, t in enumerate(texts) if "F1200" in t), -1,
        )
        idx_z1_2 = next(
            (i for i, t in enumerate(texts) if "Z1.2" in t), -1,
        )
        assert idx_m207_0 != -1
        assert idx_z1_2 != -1
        assert idx_m207_0 < idx_z1_2

        idx_m207_1 = next(
            (i for i, t in enumerate(texts) if "F1800" in t), -1,
        )
        idx_z2_2 = next(
            (i for i, t in enumerate(texts) if "Z2.2" in t), -1,
        )
        assert idx_m207_1 != -1
        assert idx_z2_2 != -1
        assert idx_m207_1 < idx_z2_2

    def test_immutable_input(self):
        """Original list is not mutated."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
        )
        lines = _lines(gcode)
        original_len = len(lines)
        levels = compute_retraction_speed_levels(20.0, 5.0, 1, 1.0, base_height=1.0)
        insert_retraction_speed_commands(lines, levels, 0.8)
        assert len(lines) == original_len
