"""Tests for filament_calibrator.pa_pattern — diamond PA calibration model."""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from filament_calibrator.pa_pattern import (
    DEFAULT_CORNER_ANGLE,
    DEFAULT_NUM_LAYERS,
    DEFAULT_PATTERN_SPACING,
    DEFAULT_SIDE_LENGTH,
    DEFAULT_WALL_COUNT,
    DEFAULT_WALL_THICKNESS,
    PAPatternConfig,
    _diamond_vertices,
    _make_diamond,
    diamond_height,
    diamond_width,
    generate_pa_pattern_stl,
    pattern_x_centers,
    total_height,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_corner_angle(self):
        assert DEFAULT_CORNER_ANGLE == 90.0

    def test_side_length(self):
        assert DEFAULT_SIDE_LENGTH == 30.0

    def test_wall_count(self):
        assert DEFAULT_WALL_COUNT == 3

    def test_num_layers(self):
        assert DEFAULT_NUM_LAYERS == 4

    def test_pattern_spacing(self):
        assert DEFAULT_PATTERN_SPACING == 2.0

    def test_wall_thickness(self):
        assert DEFAULT_WALL_THICKNESS == 1.6


# ---------------------------------------------------------------------------
# PAPatternConfig
# ---------------------------------------------------------------------------


class TestPAPatternConfig:
    def test_defaults(self):
        cfg = PAPatternConfig(num_patterns=5)
        assert cfg.num_patterns == 5
        assert cfg.corner_angle == 90.0
        assert cfg.side_length == 30.0
        assert cfg.wall_count == 3
        assert cfg.num_layers == 4
        assert cfg.pattern_spacing == 2.0
        assert cfg.wall_thickness == 1.6
        assert cfg.layer_height == 0.2
        assert cfg.filament_type == "PLA"

    def test_custom(self):
        cfg = PAPatternConfig(
            num_patterns=10,
            corner_angle=60.0,
            side_length=20.0,
            wall_count=5,
            num_layers=8,
            pattern_spacing=3.0,
            wall_thickness=2.0,
            layer_height=0.1,
            filament_type="PETG",
        )
        assert cfg.num_patterns == 10
        assert cfg.corner_angle == 60.0
        assert cfg.side_length == 20.0
        assert cfg.wall_count == 5
        assert cfg.num_layers == 8
        assert cfg.pattern_spacing == 3.0
        assert cfg.wall_thickness == 2.0
        assert cfg.layer_height == 0.1
        assert cfg.filament_type == "PETG"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


class TestDiamondWidth:
    def test_90_degree_angle(self):
        expected = 2 * 30 * math.cos(math.radians(45))
        assert diamond_width(30, 90) == pytest.approx(expected)

    def test_60_degree_angle(self):
        expected = 2 * 20 * math.cos(math.radians(30))
        assert diamond_width(20, 60) == pytest.approx(expected)

    def test_120_degree_angle(self):
        expected = 2 * 10 * math.cos(math.radians(60))
        assert diamond_width(10, 120) == pytest.approx(expected)


class TestDiamondHeight:
    def test_90_degree_angle(self):
        expected = 2 * 30 * math.sin(math.radians(45))
        assert diamond_height(30, 90) == pytest.approx(expected)

    def test_60_degree_angle(self):
        expected = 2 * 20 * math.sin(math.radians(30))
        assert diamond_height(20, 60) == pytest.approx(expected)

    def test_symmetry_at_90(self):
        """At 90 degrees, width == height."""
        assert diamond_width(30, 90) == pytest.approx(diamond_height(30, 90))


class TestTotalHeight:
    def test_default(self):
        cfg = PAPatternConfig(num_patterns=3)
        assert total_height(cfg) == pytest.approx(4 * 0.2)

    def test_custom(self):
        cfg = PAPatternConfig(num_patterns=3, num_layers=10, layer_height=0.1)
        assert total_height(cfg) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# pattern_x_centers
# ---------------------------------------------------------------------------


class TestPatternXCenters:
    def test_single_pattern_centered(self):
        cfg = PAPatternConfig(num_patterns=1)
        centers = pattern_x_centers(cfg)
        assert len(centers) == 1
        assert centers[0] == pytest.approx(0.0)

    def test_two_patterns_symmetric(self):
        cfg = PAPatternConfig(num_patterns=2)
        centers = pattern_x_centers(cfg)
        assert len(centers) == 2
        assert centers[0] == pytest.approx(-centers[1])

    def test_three_patterns_centered(self):
        cfg = PAPatternConfig(num_patterns=3)
        centers = pattern_x_centers(cfg)
        assert len(centers) == 3
        assert centers[1] == pytest.approx(0.0)

    def test_spacing_between_patterns(self):
        cfg = PAPatternConfig(num_patterns=3, pattern_spacing=2.0)
        centers = pattern_x_centers(cfg)
        dw = diamond_width(cfg.side_length, cfg.corner_angle)
        expected_stride = dw + cfg.pattern_spacing
        assert (centers[1] - centers[0]) == pytest.approx(expected_stride)
        assert (centers[2] - centers[1]) == pytest.approx(expected_stride)

    def test_count_matches_num_patterns(self):
        cfg = PAPatternConfig(num_patterns=7)
        assert len(pattern_x_centers(cfg)) == 7


# ---------------------------------------------------------------------------
# _diamond_vertices
# ---------------------------------------------------------------------------


class TestDiamondVertices:
    def test_vertex_count(self):
        verts = _diamond_vertices(0, 0, 30, 90)
        assert len(verts) == 4

    def test_center_at_origin(self):
        """Vertices should be symmetric around the centre."""
        verts = _diamond_vertices(0, 0, 30, 90)
        # right, top, left, bottom
        assert verts[0][0] == pytest.approx(-verts[2][0])
        assert verts[1][1] == pytest.approx(-verts[3][1])

    def test_center_offset(self):
        """Vertices should be offset by center_x, center_y."""
        verts = _diamond_vertices(10, 5, 30, 90)
        assert verts[0][1] == pytest.approx(5.0)  # right vertex y = center_y
        assert verts[1][0] == pytest.approx(10.0)  # top vertex x = center_x

    def test_90_degree_right_vertex(self):
        """For 90° corner angle, right vertex is at (cos(45)*side, 0)."""
        dx = 30 * math.cos(math.radians(45))
        verts = _diamond_vertices(0, 0, 30, 90)
        assert verts[0][0] == pytest.approx(dx)
        assert verts[0][1] == pytest.approx(0)


# ---------------------------------------------------------------------------
# _make_diamond (CadQuery mocked)
# ---------------------------------------------------------------------------


class TestMakeDiamond:
    @patch("filament_calibrator.pa_pattern.cq")
    def test_creates_solid_when_wall_fills_diamond(self, mock_cq):
        """If wall_thickness >= apothem, returns solid (no cut)."""
        cfg = PAPatternConfig(
            num_patterns=1,
            side_length=5.0,
            corner_angle=90.0,
            wall_thickness=100.0,
        )
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_diamond(0, 0, cfg, 1.0)

        mock_wp.cut.assert_not_called()

    @patch("filament_calibrator.pa_pattern.cq")
    def test_creates_hollow_when_wall_thinner(self, mock_cq):
        """Normal wall_thickness creates a hollow diamond (cut is called)."""
        cfg = PAPatternConfig(
            num_patterns=1,
            side_length=30.0,
            corner_angle=90.0,
            wall_thickness=1.6,
        )
        mock_outer = MagicMock()
        mock_inner = MagicMock()
        mock_cq.Workplane.side_effect = [mock_outer, mock_inner]

        mock_outer.polyline.return_value = mock_outer
        mock_outer.close.return_value = mock_outer
        mock_outer.extrude.return_value = mock_outer

        mock_inner.polyline.return_value = mock_inner
        mock_inner.close.return_value = mock_inner
        mock_inner.extrude.return_value = mock_inner

        _make_diamond(0, 0, cfg, 1.0)

        mock_outer.cut.assert_called_once_with(mock_inner)

    @patch("filament_calibrator.pa_pattern.cq")
    def test_extrude_height_passed(self, mock_cq):
        """Extrusion height is forwarded to CadQuery."""
        cfg = PAPatternConfig(
            num_patterns=1,
            side_length=30.0,
            wall_thickness=100.0,
        )
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_diamond(0, 0, cfg, 2.5)

        mock_wp.extrude.assert_called_once_with(2.5)


# ---------------------------------------------------------------------------
# generate_pa_pattern_stl (CadQuery mocked)
# ---------------------------------------------------------------------------


class TestGeneratePaPatternStl:
    @patch("filament_calibrator.pa_pattern.cq")
    def test_returns_path_and_centers(self, mock_cq, tmp_path):
        cfg = PAPatternConfig(num_patterns=3)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        result_path, x_centers = generate_pa_pattern_stl(cfg, out_path)

        assert result_path == out_path
        assert len(x_centers) == 3
        assert x_centers[1] == pytest.approx(0.0)

    @patch("filament_calibrator.pa_pattern.cq")
    def test_unions_multiple_diamonds(self, mock_cq, tmp_path):
        """Multiple diamonds are unioned together."""
        cfg = PAPatternConfig(num_patterns=3)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        assert mock_wp.union.call_count == 2

    @patch("filament_calibrator.pa_pattern.cq")
    def test_single_diamond_no_union(self, mock_cq, tmp_path):
        """Single diamond does not call union."""
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        out_path = str(tmp_path / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        mock_wp.union.assert_not_called()

    @patch("filament_calibrator.pa_pattern.cq")
    def test_exports_stl(self, mock_cq, tmp_path):
        cfg = PAPatternConfig(num_patterns=1)
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.polyline.return_value = mock_wp
        mock_wp.close.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
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
        mock_wp.cut.return_value = mock_wp

        nested = tmp_path / "sub" / "dir"
        out_path = str(nested / "test.stl")
        generate_pa_pattern_stl(cfg, out_path)

        assert nested.exists()
