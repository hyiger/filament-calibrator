"""Tests for filament_calibrator.flow_insert — feedrate G-code insertion."""
from __future__ import annotations

import pytest

import gcode_lib as gl

from filament_calibrator.flow_insert import (
    FlowLevel,
    _is_extrusion_move,
    _level_for_z,
    compute_flow_levels,
    flow_to_feedrate,
    insert_flow_rates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lines(text: str):
    return gl.parse_lines(text)


def _raw_texts(lines):
    return [line.raw for line in lines]


# ---------------------------------------------------------------------------
# FlowLevel
# ---------------------------------------------------------------------------


class TestFlowLevel:
    def test_attributes(self):
        lv = FlowLevel(flow_rate=10.0, z_start=0.0, z_end=1.0, feedrate=6666.67)
        assert lv.flow_rate == 10.0
        assert lv.z_start == 0.0
        assert lv.z_end == 1.0
        assert lv.feedrate == pytest.approx(6666.67)


# ---------------------------------------------------------------------------
# flow_to_feedrate
# ---------------------------------------------------------------------------


class TestFlowToFeedrate:
    def test_basic_calculation(self):
        # 10 mm³/s / (0.2 * 0.45) = 111.11 mm/s → 6666.67 mm/min
        result = flow_to_feedrate(10.0, 0.2, 0.45)
        assert result == pytest.approx(6666.67, rel=1e-3)

    def test_high_flow(self):
        # 20 mm³/s / (0.2 * 0.45) = 222.22 mm/s → 13333.33 mm/min
        result = flow_to_feedrate(20.0, 0.2, 0.45)
        assert result == pytest.approx(13333.33, rel=1e-3)

    def test_different_layer_height(self):
        # 10 mm³/s / (0.3 * 0.45) = 74.07 mm/s → 4444.44 mm/min
        result = flow_to_feedrate(10.0, 0.3, 0.45)
        assert result == pytest.approx(4444.44, rel=1e-3)

    def test_different_extrusion_width(self):
        # 10 mm³/s / (0.2 * 0.6) = 83.33 mm/s → 5000 mm/min
        result = flow_to_feedrate(10.0, 0.2, 0.6)
        assert result == pytest.approx(5000.0, rel=1e-3)


# ---------------------------------------------------------------------------
# compute_flow_levels
# ---------------------------------------------------------------------------


class TestComputeFlowLevels:
    def test_basic_levels(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=3,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        assert len(levels) == 3
        assert levels[0].flow_rate == pytest.approx(5.0)
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(1.0)
        assert levels[1].flow_rate == pytest.approx(6.0)
        assert levels[1].z_start == pytest.approx(1.0)
        assert levels[1].z_end == pytest.approx(2.0)
        assert levels[2].flow_rate == pytest.approx(7.0)
        assert levels[2].z_start == pytest.approx(2.0)
        assert levels[2].z_end == pytest.approx(3.0)

    def test_feedrate_computed(self):
        levels = compute_flow_levels(
            start_flow=10.0, flow_step=5.0, num_levels=2,
            level_height=2.0, layer_height=0.2, extrusion_width=0.45,
        )
        expected_f0 = flow_to_feedrate(10.0, 0.2, 0.45)
        expected_f1 = flow_to_feedrate(15.0, 0.2, 0.45)
        assert levels[0].feedrate == pytest.approx(expected_f0)
        assert levels[1].feedrate == pytest.approx(expected_f1)

    def test_single_level(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=1,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        assert len(levels) == 1
        assert levels[0].flow_rate == pytest.approx(5.0)

    def test_zero_levels(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=0,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        assert levels == []

    def test_custom_level_height(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=0.5, num_levels=4,
            level_height=2.5, layer_height=0.2, extrusion_width=0.45,
        )
        assert levels[0].z_start == pytest.approx(0.0)
        assert levels[0].z_end == pytest.approx(2.5)
        assert levels[3].z_start == pytest.approx(7.5)
        assert levels[3].z_end == pytest.approx(10.0)
        assert levels[3].flow_rate == pytest.approx(6.5)


# ---------------------------------------------------------------------------
# _level_for_z
# ---------------------------------------------------------------------------


class TestLevelForZ:
    def test_in_first_level(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=3,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        assert _level_for_z(0.5, levels).flow_rate == pytest.approx(5.0)

    def test_in_second_level(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=3,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        assert _level_for_z(1.5, levels).flow_rate == pytest.approx(6.0)

    def test_at_level_boundary(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=3,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        # z_start is inclusive
        assert _level_for_z(1.0, levels).flow_rate == pytest.approx(6.0)

    def test_below_first_level(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=3,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        # z=0.0 is at the start of level 0, should match
        assert _level_for_z(0.0, levels) is not None

    def test_above_last_level(self):
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=3,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        assert _level_for_z(3.5, levels) is None

    def test_empty_levels(self):
        assert _level_for_z(5.0, []) is None


# ---------------------------------------------------------------------------
# _is_extrusion_move
# ---------------------------------------------------------------------------


class TestIsExtrusionMove:
    def test_g1_with_x_and_e(self):
        line = gl.parse_line("G1 X10 E1 F1000")
        assert _is_extrusion_move(line) is True

    def test_g1_with_y_and_e(self):
        line = gl.parse_line("G1 Y10 E1 F1000")
        assert _is_extrusion_move(line) is True

    def test_g1_with_xy_and_e(self):
        line = gl.parse_line("G1 X10 Y20 E1.5 F1000")
        assert _is_extrusion_move(line) is True

    def test_g1_z_only_not_extrusion(self):
        line = gl.parse_line("G1 Z1.0 F1000")
        assert _is_extrusion_move(line) is False

    def test_g1_retraction_not_extrusion(self):
        """E-only move (retraction) is not a lateral extrusion."""
        line = gl.parse_line("G1 E-1.0 F3000")
        assert _is_extrusion_move(line) is False

    def test_g0_travel_not_extrusion(self):
        line = gl.parse_line("G0 X10 Y20 F5000")
        assert _is_extrusion_move(line) is False

    def test_non_move_command(self):
        line = gl.parse_line("M104 S200")
        assert _is_extrusion_move(line) is False

    def test_comment_line(self):
        line = gl.parse_line("; this is a comment")
        assert _is_extrusion_move(line) is False


# ---------------------------------------------------------------------------
# insert_flow_rates
# ---------------------------------------------------------------------------


class TestInsertFlowRates:
    def test_basic_feedrate_override(self):
        """Extrusion moves get their F parameter overridden."""
        gcode = (
            "G28\n"
            "G1 Z0.2 F1000\n"
            "G1 X10 E1 F1000\n"
            "G1 X20 E2 F1000\n"
        )
        lines = _lines(gcode)
        levels = compute_flow_levels(
            start_flow=10.0, flow_step=5.0, num_levels=1,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        result = insert_flow_rates(lines, levels)
        texts = _raw_texts(result)

        # Extrusion moves should have modified F
        expected_f = flow_to_feedrate(10.0, 0.2, 0.45)
        extrusion_lines = [t for t in texts if "E1" in t or "E2" in t]
        for line_text in extrusion_lines:
            assert f"F{expected_f:.5f}" in line_text

    def test_non_extrusion_moves_unchanged(self):
        """Travel moves and Z moves pass through without F change."""
        gcode = (
            "G28\n"
            "G0 X10 Y10 F5000\n"
            "G1 Z0.2 F1000\n"
            "G1 X20 E1 F1000\n"
        )
        lines = _lines(gcode)
        levels = compute_flow_levels(
            start_flow=10.0, flow_step=5.0, num_levels=1,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        result = insert_flow_rates(lines, levels)
        texts = _raw_texts(result)

        # G28 unchanged
        assert texts[0] == "G28"
        # G0 travel unchanged
        assert "F5000" in texts[1]

    def test_level_transition(self):
        """Feedrate changes when Z crosses into a new level."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1 F1000\n"
            "G1 Z1.2 F1000\n"
            "G1 X20 E2 F1000\n"
        )
        lines = _lines(gcode)
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=5.0, num_levels=2,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        result = insert_flow_rates(lines, levels)
        texts = _raw_texts(result)

        # First extrusion at Z=0.2 (level 0, flow=5)
        f0 = flow_to_feedrate(5.0, 0.2, 0.45)
        # Second extrusion at Z=1.2 (level 1, flow=10)
        f1 = flow_to_feedrate(10.0, 0.2, 0.45)

        # Find the extrusion lines
        e1_line = [t for t in texts if "E1" in t and "X10" in t][0]
        e2_line = [t for t in texts if "E2" in t and "X20" in t][0]

        assert f"F{f0:.5f}" in e1_line
        assert f"F{f1:.5f}" in e2_line

    def test_empty_levels_no_change(self):
        """Empty levels list means no modifications."""
        gcode = "G28\nG1 X10 E1 F1000\n"
        lines = _lines(gcode)
        result = insert_flow_rates(lines, [])
        assert len(result) == len(lines)
        assert _raw_texts(result) == _raw_texts(lines)

    def test_empty_lines(self):
        result = insert_flow_rates([], compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=3,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        ))
        assert result == []

    def test_above_last_level_keeps_feedrate(self):
        """Moves above the last level keep the last level's feedrate."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1 F1000\n"
            "G1 Z100.0 F1000\n"
            "G1 X20 E2 F1000\n"
        )
        lines = _lines(gcode)
        levels = compute_flow_levels(
            start_flow=5.0, flow_step=1.0, num_levels=1,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        result = insert_flow_rates(lines, levels)
        texts = _raw_texts(result)

        # Second extrusion at Z=100 — above levels, uses last known level
        f0 = flow_to_feedrate(5.0, 0.2, 0.45)
        e2_line = [t for t in texts if "E2" in t and "X20" in t][0]
        assert f"F{f0:.5f}" in e2_line

    def test_immutable_input(self):
        """Original lines list is not mutated."""
        gcode = "G1 Z0.2 F1000\nG1 X10 E1 F1000\n"
        lines = _lines(gcode)
        original_raws = [line.raw for line in lines]
        levels = compute_flow_levels(
            start_flow=10.0, flow_step=5.0, num_levels=1,
            level_height=1.0, layer_height=0.2, extrusion_width=0.45,
        )
        insert_flow_rates(lines, levels)
        assert [line.raw for line in lines] == original_raws
