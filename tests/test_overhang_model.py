"""Tests for filament_calibrator.overhang_model -- overhang test generation."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import filament_calibrator.overhang_model as mod

from filament_calibrator.overhang_model import (
    BASE_HEIGHT,
    BASE_MARGIN,
    DEFAULT_ANGLES,
    SURFACE_LENGTH,
    SURFACE_SPACING,
    SURFACE_THICKNESS,
    SURFACE_WIDTH,
    WALL_HEIGHT,
    WALL_THICKNESS,
    OverhangTestConfig,
    _ensure_cq,
    _make_base,
    _make_overhang_surface,
    _make_overhang_test,
    _make_wall,
    generate_overhang_stl,
    total_depth,
    total_width,
)


# ---------------------------------------------------------------------------
# _ensure_cq
# ---------------------------------------------------------------------------


class TestEnsureCq:
    def test_imports_cadquery_when_none(self):
        saved = mod.cq
        try:
            mod.cq = None
            mock_cq = MagicMock()
            with patch.object(mod, "_ensure_cq_impl", return_value=mock_cq):
                _ensure_cq()
            assert mod.cq is mock_cq
        finally:
            mod.cq = saved


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_defaults(self):
        assert WALL_THICKNESS == 5.0
        assert WALL_HEIGHT == 20.0
        assert SURFACE_LENGTH == 25.0
        assert SURFACE_WIDTH == 15.0
        assert SURFACE_THICKNESS == 2.0
        assert SURFACE_SPACING == 3.0
        assert BASE_HEIGHT == 1.0
        assert BASE_MARGIN == 5.0
        assert DEFAULT_ANGLES == (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70)


# ---------------------------------------------------------------------------
# OverhangTestConfig
# ---------------------------------------------------------------------------


class TestOverhangTestConfig:
    def test_defaults(self):
        config = OverhangTestConfig()
        assert config.angles == DEFAULT_ANGLES
        assert config.wall_thickness == WALL_THICKNESS
        assert config.wall_height == WALL_HEIGHT
        assert config.surface_length == SURFACE_LENGTH
        assert config.surface_width == SURFACE_WIDTH
        assert config.surface_thickness == SURFACE_THICKNESS
        assert config.surface_spacing == SURFACE_SPACING
        assert config.base_height == BASE_HEIGHT
        assert config.base_margin == BASE_MARGIN
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = OverhangTestConfig(
            angles=(30, 45, 60),
            wall_thickness=8.0,
            wall_height=25.0,
            surface_length=30.0,
            surface_width=20.0,
            surface_thickness=3.0,
            surface_spacing=5.0,
            base_height=2.0,
            base_margin=8.0,
            filament_type="ABS",
        )
        assert config.angles == (30, 45, 60)
        assert config.wall_thickness == 8.0
        assert config.wall_height == 25.0
        assert config.surface_length == 30.0
        assert config.surface_width == 20.0
        assert config.surface_thickness == 3.0
        assert config.surface_spacing == 5.0
        assert config.base_height == 2.0
        assert config.base_margin == 8.0
        assert config.filament_type == "ABS"


# ---------------------------------------------------------------------------
# total_width
# ---------------------------------------------------------------------------


class TestTotalWidth:
    def test_default_config(self):
        config = OverhangTestConfig()
        n = len(config.angles)
        expected = n * (config.surface_width + config.surface_spacing) - config.surface_spacing
        assert total_width(config) == expected

    def test_single_angle(self):
        config = OverhangTestConfig(angles=(45,))
        assert total_width(config) == config.surface_width


# ---------------------------------------------------------------------------
# total_depth
# ---------------------------------------------------------------------------


class TestTotalDepth:
    def test_default_config(self):
        config = OverhangTestConfig()
        assert total_depth(config) == config.wall_thickness + config.surface_length

    def test_custom_config(self):
        config = OverhangTestConfig(wall_thickness=8.0, surface_length=30.0)
        assert total_depth(config) == 38.0


# ---------------------------------------------------------------------------
# _make_base (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeBase:
    @patch("filament_calibrator.overhang_model.cq")
    def test_creates_base_box(self, mock_cq):
        config = OverhangTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp

        _make_base(config)

        mock_cq.Workplane.assert_called_once_with("XY")
        tw = total_width(config)
        td = total_depth(config)
        base_x = tw + 2 * config.base_margin
        base_y = td + 2 * config.base_margin
        box_call = mock_wp.box.call_args
        assert box_call == call(
            base_x, base_y, config.base_height,
            centered=(True, True, False),
        )


# ---------------------------------------------------------------------------
# _make_wall (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeWall:
    @patch("filament_calibrator.overhang_model.cq")
    def test_creates_wall_box_and_translates(self, mock_cq):
        config = OverhangTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_wall(config)

        tw = total_width(config)
        wall_x = tw + 2 * config.base_margin
        mock_wp.box.assert_called_once_with(
            wall_x,
            config.wall_thickness,
            config.wall_height,
            centered=(True, True, False),
        )
        mock_wp.translate.assert_called_once()
        translate_args = mock_wp.translate.call_args[0][0]
        assert translate_args[2] == config.base_height


# ---------------------------------------------------------------------------
# _make_overhang_surface (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeOverhangSurface:
    @patch("filament_calibrator.overhang_model.cq")
    def test_creates_surface_box_and_rotates(self, mock_cq):
        config = OverhangTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.rotate.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_overhang_surface(config, 45, 0.0)

        overlap = config.wall_thickness / 2.0
        mock_wp.box.assert_called_once_with(
            config.surface_width,
            config.surface_length + overlap,
            config.surface_thickness,
            centered=(True, False, False),
        )
        mock_wp.rotate.assert_called_once()
        # Two translates: one to shift slab into wall, one for final position
        assert mock_wp.translate.call_count == 2

    @patch("filament_calibrator.overhang_model.cq")
    def test_rotation_angle(self, mock_cq):
        """Rotation from horizontal should be -(90 - angle)."""
        config = OverhangTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.rotate.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_overhang_surface(config, 30, 5.0)

        rot_call = mock_wp.rotate.call_args
        # rotate((0,0,0), (1,0,0), -(90-30)) = -60
        assert rot_call[0][0] == (0, 0, 0)
        assert rot_call[0][1] == (1, 0, 0)
        assert rot_call[0][2] == -60.0

        # First translate shifts slab into wall, second positions at wall
        assert mock_wp.translate.call_count == 2
        overlap_translate = mock_wp.translate.call_args_list[0]
        assert overlap_translate[0][0] == (0, -config.wall_thickness / 2.0, 0)


# ---------------------------------------------------------------------------
# _make_overhang_test (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeOverhangTest:
    @patch("filament_calibrator.overhang_model.cq")
    def test_union_calls(self, mock_cq):
        config = OverhangTestConfig(angles=(30, 45, 60))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.rotate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_overhang_test(config)

        # 1 wall union + 3 surface unions = 4 total
        assert mock_wp.union.call_count == 4

    @patch("filament_calibrator.overhang_model.cq")
    def test_single_angle(self, mock_cq):
        config = OverhangTestConfig(angles=(45,))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.rotate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_overhang_test(config)

        # 1 wall + 1 surface = 2
        assert mock_wp.union.call_count == 2


# ---------------------------------------------------------------------------
# generate_overhang_stl
# ---------------------------------------------------------------------------


class TestGenerateOverhangStl:
    @patch("filament_calibrator.overhang_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.rotate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = tmp_path / "nested" / "dir" / "overhang.stl"
        config = OverhangTestConfig()
        result = generate_overhang_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.overhang_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.rotate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = OverhangTestConfig()
        result = generate_overhang_stl(config, output)

        assert result == output

    @patch("filament_calibrator.overhang_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.rotate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = OverhangTestConfig()
        generate_overhang_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output
