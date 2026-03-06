"""Tests for filament_calibrator.pa_pattern — chevron PA calibration model."""
from __future__ import annotations

import math
from unittest.mock import MagicMock, call, patch

import pytest

from filament_calibrator.pa_pattern import (
    DEFAULT_ARM_LENGTH,
    DEFAULT_CORNER_ANGLE,
    DEFAULT_FRAME_OFFSET,
    DEFAULT_NUM_LAYERS,
    DEFAULT_PATTERN_SPACING,
    DEFAULT_WALL_COUNT,
    DEFAULT_WALL_THICKNESS,
    PAPatternConfig,
    _chevron_outline,
    _make_chevron,
    _make_frame,
    _make_labels,
    chevron_x_extent,
    chevron_y_extent,
    generate_pa_pattern_stl,
    pattern_x_tips,
    tip_spacing,
    total_height,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_corner_angle(self):
        assert DEFAULT_CORNER_ANGLE == 90.0

    def test_arm_length(self):
        assert DEFAULT_ARM_LENGTH == 40.0

    def test_wall_count(self):
        assert DEFAULT_WALL_COUNT == 3

    def test_num_layers(self):
        assert DEFAULT_NUM_LAYERS == 4

    def test_pattern_spacing(self):
        assert DEFAULT_PATTERN_SPACING == 2.0

    def test_wall_thickness(self):
        assert DEFAULT_WALL_THICKNESS == 1.6

    def test_frame_offset(self):
        assert DEFAULT_FRAME_OFFSET == 3.0


# ---------------------------------------------------------------------------
# PAPatternConfig
# ---------------------------------------------------------------------------


class TestPAPatternConfig:
    def test_defaults(self):
        cfg = PAPatternConfig(num_patterns=5)
        assert cfg.num_patterns == 5
        assert cfg.corner_angle == 90.0
        assert cfg.arm_length == 40.0
        assert cfg.wall_count == 3
        assert cfg.num_layers == 4
        assert cfg.pattern_spacing == 2.0
        assert cfg.wall_thickness == 1.6
        assert cfg.frame_offset == 3.0
        assert cfg.layer_height == 0.2
        assert cfg.filament_type == "PLA"

    def test_custom(self):
        cfg = PAPatternConfig(
            num_patterns=10,
            corner_angle=60.0,
            arm_length=20.0,
            wall_count=5,
            num_layers=8,
            pattern_spacing=3.0,
            wall_thickness=2.0,
            frame_offset=5.0,
            layer_height=0.1,
            filament_type="PETG",
        )
        assert cfg.num_patterns == 10
        assert cfg.corner_angle == 60.0
        assert cfg.arm_length == 20.0
        assert cfg.wall_count == 5
        assert cfg.num_layers == 8
        assert cfg.pattern_spacing == 3.0
        assert cfg.wall_thickness == 2.0
        assert cfg.frame_offset == 5.0
        assert cfg.layer_height == 0.1
        assert cfg.filament_type == "PETG"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


class TestChevronXExtent:
    def test_90_degree_angle(self):
        expected = 40.0 * math.cos(math.radians(45))
        assert chevron_x_extent(40.0, 90.0) == pytest.approx(expected)

    def test_60_degree_angle(self):
        expected = 20.0 * math.cos(math.radians(30))
        assert chevron_x_extent(20.0, 60.0) == pytest.approx(expected)

    def test_120_degree_angle(self):
        expected = 10.0 * math.cos(math.radians(60))
        assert chevron_x_extent(10.0, 120.0) == pytest.approx(expected)


class TestChevronYExtent:
    def test_90_degree_angle(self):
        expected = 2.0 * 40.0 * math.sin(math.radians(45))
        assert chevron_y_extent(40.0, 90.0) == pytest.approx(expected)

    def test_60_degree_angle(self):
        expected = 2.0 * 20.0 * math.sin(math.radians(30))
        assert chevron_y_extent(20.0, 60.0) == pytest.approx(expected)

    def test_symmetry_at_90(self):
        """At 90 degrees, x_extent == y_extent / 2 (since y = 2 * arm * sin)."""
        x = chevron_x_extent(40.0, 90.0)
        y = chevron_y_extent(40.0, 90.0)
        assert y == pytest.approx(2.0 * x)


class TestTotalHeight:
    def test_default(self):
        cfg = PAPatternConfig(num_patterns=3)
        assert total_height(cfg) == pytest.approx(4 * 0.2)

    def test_custom(self):
        cfg = PAPatternConfig(num_patterns=3, num_layers=10, layer_height=0.1)
        assert total_height(cfg) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# tip_spacing
# ---------------------------------------------------------------------------


class TestTipSpacing:
    def test_90_degree(self):
        cfg = PAPatternConfig(num_patterns=3, pattern_spacing=2.0, corner_angle=90.0)
        half = math.radians(45)
        expected = 2.0 / math.sin(half)
        assert tip_spacing(cfg) == pytest.approx(expected)

    def test_60_degree(self):
        cfg = PAPatternConfig(num_patterns=3, pattern_spacing=3.0, corner_angle=60.0)
        half = math.radians(30)
        expected = 3.0 / math.sin(half)
        assert tip_spacing(cfg) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# pattern_x_tips
# ---------------------------------------------------------------------------


class TestPatternXTips:
    def test_single_pattern_centered(self):
        cfg = PAPatternConfig(num_patterns=1)
        tips = pattern_x_tips(cfg)
        assert len(tips) == 1
        assert tips[0] == pytest.approx(0.0)

    def test_two_patterns_symmetric(self):
        cfg = PAPatternConfig(num_patterns=2)
        tips = pattern_x_tips(cfg)
        assert len(tips) == 2
        assert tips[0] == pytest.approx(-tips[1])

    def test_three_patterns_centered(self):
        cfg = PAPatternConfig(num_patterns=3)
        tips = pattern_x_tips(cfg)
        assert len(tips) == 3
        assert tips[1] == pytest.approx(0.0)

    def test_spacing_between_tips(self):
        cfg = PAPatternConfig(num_patterns=3, pattern_spacing=2.0, corner_angle=90.0)
        tips = pattern_x_tips(cfg)
        expected_dx = tip_spacing(cfg)
        # pattern_x_tips rounds to 4 decimal places, so use abs tolerance.
        assert (tips[1] - tips[0]) == pytest.approx(expected_dx, abs=1e-4)
        assert (tips[2] - tips[1]) == pytest.approx(expected_dx, abs=1e-4)

    def test_count_matches_num_patterns(self):
        cfg = PAPatternConfig(num_patterns=7)
        assert len(pattern_x_tips(cfg)) == 7


# ---------------------------------------------------------------------------
# _chevron_outline
# ---------------------------------------------------------------------------


class TestChevronOutline:
    def test_vertex_count(self):
        verts = _chevron_outline(0.0, 40.0, 90.0, 1.6)
        assert len(verts) == 6

    def test_y_symmetry(self):
        """Vertices should be symmetric in Y around the tip axis."""
        verts = _chevron_outline(0.0, 40.0, 90.0, 1.6)
        # verts[0] = outer tip (y=0), verts[3] = inner tip (y=0)
        assert verts[0][1] == pytest.approx(0.0)
        assert verts[3][1] == pytest.approx(0.0)
        # Top and bottom outer vertices are Y-symmetric.
        assert verts[1][1] == pytest.approx(-verts[5][1])
        # Top and bottom inner vertices are Y-symmetric.
        assert verts[2][1] == pytest.approx(-verts[4][1])

    def test_tip_position(self):
        """Outer tip x > inner tip x (chevron points right)."""
        verts = _chevron_outline(0.0, 40.0, 90.0, 1.6)
        outer_tip_x = verts[0][0]
        inner_tip_x = verts[3][0]
        assert outer_tip_x > inner_tip_x

    def test_inner_notch(self):
        """Inner tip (notch) is at tip_x - hw / sin(half_angle)."""
        tip_x = 5.0
        w = 1.6
        hw = w / 2.0
        half = math.radians(45)
        expected_inner = tip_x - hw / math.sin(half)
        verts = _chevron_outline(tip_x, 40.0, 90.0, w)
        assert verts[3][0] == pytest.approx(expected_inner)

    def test_outer_tip(self):
        """Outer tip is at tip_x + hw / sin(half_angle)."""
        tip_x = 5.0
        w = 1.6
        hw = w / 2.0
        half = math.radians(45)
        expected_outer = tip_x + hw / math.sin(half)
        verts = _chevron_outline(tip_x, 40.0, 90.0, w)
        assert verts[0][0] == pytest.approx(expected_outer)

    def test_offset_tip_x(self):
        """Vertices should shift horizontally when tip_x changes."""
        verts_0 = _chevron_outline(0.0, 40.0, 90.0, 1.6)
        verts_10 = _chevron_outline(10.0, 40.0, 90.0, 1.6)
        for v0, v10 in zip(verts_0, verts_10):
            assert v10[0] == pytest.approx(v0[0] + 10.0)
            assert v10[1] == pytest.approx(v0[1])


# ---------------------------------------------------------------------------
# _make_chevron (CadQuery mocked)
# ---------------------------------------------------------------------------


class TestMakeChevron:
    @patch("filament_calibrator.pa_pattern.cq")
    def test_calls_polyline_close_extrude(self, mock_cq):
        """Chevron is built with polyline + close + extrude."""
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_chevron(0.0, cfg, 1.0)

        mock_cq.Workplane.assert_called_once_with("XY")
        mock_wp.polyline.assert_called_once()
        mock_wp.close.assert_called_once()
        mock_wp.extrude.assert_called_once_with(1.0)

    @patch("filament_calibrator.pa_pattern.cq")
    def test_extrude_height_passed(self, mock_cq):
        """Extrusion height is forwarded to CadQuery."""
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_chevron(5.0, cfg, 2.5)

        mock_wp.extrude.assert_called_once_with(2.5)

    @patch("filament_calibrator.pa_pattern.cq")
    def test_polyline_receives_6_vertices(self, mock_cq):
        """The polyline call receives the 6-vertex chevron outline."""
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_chevron(0.0, cfg, 1.0)

        verts_arg = mock_wp.polyline.call_args[0][0]
        assert len(verts_arg) == 6


# ---------------------------------------------------------------------------
# _make_frame (CadQuery mocked)
# ---------------------------------------------------------------------------


class TestMakeFrame:
    @patch("filament_calibrator.pa_pattern.cq")
    def test_outer_and_inner_rectangles(self, mock_cq):
        """Frame creates an outer box and cuts an inner box from it."""
        cfg = PAPatternConfig(num_patterns=3)
        x_tips = pattern_x_tips(cfg)

        mock_outer = MagicMock()
        mock_inner = MagicMock()
        mock_cq.Workplane.side_effect = [mock_outer, mock_inner]

        mock_outer.moveTo.return_value = mock_outer
        mock_outer.lineTo.return_value = mock_outer
        mock_outer.close.return_value = mock_outer
        mock_outer.extrude.return_value = mock_outer
        mock_outer.cut.return_value = mock_outer

        mock_inner.moveTo.return_value = mock_inner
        mock_inner.lineTo.return_value = mock_inner
        mock_inner.close.return_value = mock_inner
        mock_inner.extrude.return_value = mock_inner

        _make_frame(cfg, x_tips, 0.8)

        # Outer rectangle: moveTo + 3 lineTo + close + extrude.
        assert mock_outer.moveTo.call_count == 1
        assert mock_outer.lineTo.call_count == 3
        mock_outer.close.assert_called_once()
        mock_outer.extrude.assert_called_once_with(0.8)

        # Inner rectangle: moveTo + 3 lineTo + close + extrude.
        assert mock_inner.moveTo.call_count == 1
        assert mock_inner.lineTo.call_count == 3
        mock_inner.close.assert_called_once()
        mock_inner.extrude.assert_called_once_with(0.8)

        # Cut inner from outer.
        mock_outer.cut.assert_called_once_with(mock_inner)

    @patch("filament_calibrator.pa_pattern.cq")
    def test_two_workplanes_created(self, mock_cq):
        """Two Workplane("XY") calls: one for outer, one for inner."""
        cfg = PAPatternConfig(num_patterns=2)
        x_tips = pattern_x_tips(cfg)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        _make_frame(cfg, x_tips, 0.8)

        assert mock_cq.Workplane.call_count == 2
        mock_cq.Workplane.assert_any_call("XY")


# ---------------------------------------------------------------------------
# _make_labels (CadQuery mocked)
# ---------------------------------------------------------------------------


class TestMakeLabels:
    @patch("filament_calibrator.pa_pattern.cq")
    def test_text_calls_for_each_pa_value(self, mock_cq):
        """A text solid is created for each PA value."""
        cfg = PAPatternConfig(num_patterns=3)
        x_tips = pattern_x_tips(cfg)
        pa_values = [0.02, 0.04, 0.06]

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_labels(cfg, x_tips, pa_values, 0.8)

        # One text call per PA value.
        assert mock_wp.text.call_count == 3

    @patch("filament_calibrator.pa_pattern.cq")
    def test_text_content_formatting(self, mock_cq):
        """Each label uses f'{pa:.2f}' formatting."""
        cfg = PAPatternConfig(num_patterns=2)
        x_tips = pattern_x_tips(cfg)
        pa_values = [0.03, 0.05]

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_labels(cfg, x_tips, pa_values, 0.8)

        text_calls = mock_wp.text.call_args_list
        assert text_calls[0][0][0] == "0.03"
        assert text_calls[1][0][0] == "0.05"

    @patch("filament_calibrator.pa_pattern.cq")
    def test_bar_created_with_box(self, mock_cq):
        """Label bar is created using box()."""
        cfg = PAPatternConfig(num_patterns=2)
        x_tips = pattern_x_tips(cfg)
        pa_values = [0.01, 0.02]

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_labels(cfg, x_tips, pa_values, 0.8)

        mock_wp.box.assert_called_once()

    @patch("filament_calibrator.pa_pattern.cq")
    def test_union_called_for_each_label(self, mock_cq):
        """Each text solid is unioned onto the bar."""
        cfg = PAPatternConfig(num_patterns=3)
        x_tips = pattern_x_tips(cfg)
        pa_values = [0.01, 0.02, 0.03]

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_labels(cfg, x_tips, pa_values, 0.8)

        # One union per PA value.
        assert mock_wp.union.call_count == 3

    @patch("filament_calibrator.pa_pattern.cq")
    def test_workplane_offset_at_height(self, mock_cq):
        """Text workplane is offset to the top of the bar (height)."""
        cfg = PAPatternConfig(num_patterns=1)
        x_tips = pattern_x_tips(cfg)
        pa_values = [0.04]

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_labels(cfg, x_tips, pa_values, 0.8)

        mock_wp.workplane.assert_called_once_with(offset=0.8)

    @patch("filament_calibrator.pa_pattern.cq")
    def test_label_depth_is_layer_height(self, mock_cq):
        """Label extrusion depth equals one layer height."""
        cfg = PAPatternConfig(num_patterns=1, layer_height=0.15)
        x_tips = pattern_x_tips(cfg)
        pa_values = [0.04]

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_labels(cfg, x_tips, pa_values, 0.8)

        text_call = mock_wp.text.call_args
        # text(label_text, font_size, label_depth, combine=False)
        label_depth = text_call[0][2]
        assert label_depth == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# generate_pa_pattern_stl (CadQuery mocked)
# ---------------------------------------------------------------------------


class TestGeneratePaPatternStl:
    @patch("filament_calibrator.pa_pattern.cq")
    def test_returns_path_and_tips(self, mock_cq, tmp_path):
        cfg = PAPatternConfig(num_patterns=3)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        result_path, x_tips = generate_pa_pattern_stl(cfg, out_path)

        assert result_path == out_path
        assert len(x_tips) == 3
        assert x_tips[1] == pytest.approx(0.0)

    @patch("filament_calibrator.pa_pattern.cq")
    def test_unions_multiple_chevrons_and_frame(self, mock_cq, tmp_path):
        """Multiple chevrons are unioned together, then frame is unioned."""
        cfg = PAPatternConfig(num_patterns=3)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        # 2 unions for chevrons (first is assigned, 2nd and 3rd unioned)
        # + 1 union for frame = 3 total.
        assert mock_wp.union.call_count == 3

    @patch("filament_calibrator.pa_pattern.cq")
    def test_single_chevron_still_has_frame_union(self, mock_cq, tmp_path):
        """Single chevron doesn't union other chevrons but still unions frame."""
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        # No chevron-to-chevron unions, but 1 frame union.
        assert mock_wp.union.call_count == 1

    @patch("filament_calibrator.pa_pattern.cq")
    def test_exports_stl(self, mock_cq, tmp_path):
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.pa_pattern.cq")
    def test_creates_output_directory(self, mock_cq, tmp_path):
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        nested = tmp_path / "sub" / "dir"
        out_path = str(nested / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        assert nested.exists()

    @patch("filament_calibrator.pa_pattern.cq")
    def test_with_pa_values_adds_labels(self, mock_cq, tmp_path):
        """When pa_values is provided and matches length, labels are added."""
        cfg = PAPatternConfig(num_patterns=3)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.text.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        pa_values = [0.02, 0.04, 0.06]
        generate_pa_pattern_stl(cfg, out_path, pa_values=pa_values)

        # 2 chevron unions + 1 frame union + 3 label text unions
        # (inside _make_labels) + 1 labels-to-result union = 7.
        assert mock_wp.union.call_count == 7

    @patch("filament_calibrator.pa_pattern.cq")
    def test_pa_values_wrong_length_skips_labels(self, mock_cq, tmp_path):
        """When pa_values length doesn't match, labels are skipped."""
        cfg = PAPatternConfig(num_patterns=3)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        pa_values = [0.02, 0.04]  # Only 2 values for 3 patterns.
        generate_pa_pattern_stl(cfg, out_path, pa_values=pa_values)

        # 2 chevron unions + 1 frame union = 3 (no label union).
        assert mock_wp.union.call_count == 3

    @patch("filament_calibrator.pa_pattern.cq")
    def test_pa_values_none_skips_labels(self, mock_cq, tmp_path):
        """When pa_values is None, labels are skipped."""
        cfg = PAPatternConfig(num_patterns=2)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        generate_pa_pattern_stl(cfg, out_path, pa_values=None)

        # 1 chevron union + 1 frame union = 2 (no label union).
        assert mock_wp.union.call_count == 2

    @patch("filament_calibrator.pa_pattern.cq")
    def test_export_receives_result_and_path(self, mock_cq, tmp_path):
        """export() is called with the final result and the output path."""
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.moveTo.return_value = mock_wp
        mock_wp.lineTo.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        export_args = mock_cq.exporters.export.call_args[0]
        assert export_args[1] == out_path
