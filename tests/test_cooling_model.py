"""Tests for filament_calibrator.cooling_model — single-tower cooling geometry."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import filament_calibrator.cooling_model as mod

from filament_calibrator.cooling_model import (
    BASE_HEIGHT,
    BASE_LENGTH,
    BASE_WIDTH,
    LEVEL_HEIGHT,
    TOWER_DIAMETER,
    CoolingTowerConfig,
    _ensure_cq,
    _make_base,
    _make_cooling_tower,
    _make_tower,
    generate_cooling_tower_stl,
    total_height,
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
    def test_tower_diameter(self):
        assert TOWER_DIAMETER == 15.0

    def test_base_length(self):
        assert BASE_LENGTH == 30.0

    def test_base_width(self):
        assert BASE_WIDTH == 30.0

    def test_base_height(self):
        assert BASE_HEIGHT == 1.0

    def test_level_height(self):
        assert LEVEL_HEIGHT == 5.0


# ---------------------------------------------------------------------------
# CoolingTowerConfig
# ---------------------------------------------------------------------------


class TestCoolingTowerConfig:
    def test_defaults(self):
        config = CoolingTowerConfig(num_levels=10)
        assert config.num_levels == 10
        assert config.level_height == LEVEL_HEIGHT
        assert config.tower_diameter == TOWER_DIAMETER
        assert config.base_length == BASE_LENGTH
        assert config.base_width == BASE_WIDTH
        assert config.base_height == BASE_HEIGHT
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = CoolingTowerConfig(
            num_levels=20,
            level_height=2.0,
            tower_diameter=20.0,
            base_length=40.0,
            base_width=35.0,
            base_height=2.0,
            filament_type="PETG",
        )
        assert config.num_levels == 20
        assert config.level_height == 2.0
        assert config.tower_diameter == 20.0
        assert config.base_length == 40.0
        assert config.base_width == 35.0
        assert config.base_height == 2.0
        assert config.filament_type == "PETG"


# ---------------------------------------------------------------------------
# total_height
# ---------------------------------------------------------------------------


class TestTotalHeight:
    def test_default_config(self):
        config = CoolingTowerConfig(num_levels=10)
        assert total_height(config) == pytest.approx(51.0)

    def test_custom_level_height(self):
        config = CoolingTowerConfig(num_levels=5, level_height=2.0)
        assert total_height(config) == pytest.approx(11.0)

    def test_custom_base_height(self):
        config = CoolingTowerConfig(
            num_levels=10, level_height=5.0, base_height=2.0,
        )
        assert total_height(config) == pytest.approx(52.0)

    def test_single_level(self):
        config = CoolingTowerConfig(num_levels=1)
        assert total_height(config) == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# _make_base (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeBase:
    @patch("filament_calibrator.cooling_model.cq")
    def test_creates_box(self, mock_cq):
        """Base plate is created as a box with correct dimensions."""
        config = CoolingTowerConfig(num_levels=5)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp

        _make_base(config)

        mock_cq.Workplane.assert_called_with("XY")
        mock_wp.box.assert_called_once_with(
            config.base_length,
            config.base_width,
            config.base_height,
            centered=(True, True, False),
        )


# ---------------------------------------------------------------------------
# _make_tower (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeTower:
    @patch("filament_calibrator.cooling_model.cq")
    def test_creates_cylinder(self, mock_cq):
        """Tower is created as a circle extruded to height."""
        config = CoolingTowerConfig(num_levels=5)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_tower(config)

        height = config.num_levels * config.level_height
        mock_wp.circle.assert_called_once_with(config.tower_diameter / 2.0)
        mock_wp.extrude.assert_called_once_with(height)
        mock_wp.translate.assert_called_once_with(
            (0, 0, config.base_height),
        )


# ---------------------------------------------------------------------------
# _make_cooling_tower (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeCoolingTower:
    @patch("filament_calibrator.cooling_model.cq")
    def test_creates_base_and_tower(self, mock_cq):
        """Model consists of a base plate and one cylindrical tower."""
        config = CoolingTowerConfig(num_levels=5)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_cooling_tower(config)

        # base + 1 tower = 2 Workplane("XY") calls
        assert mock_cq.Workplane.call_count == 2
        # One union call (base + tower)
        assert mock_wp.union.call_count == 1


# ---------------------------------------------------------------------------
# generate_cooling_tower_stl
# ---------------------------------------------------------------------------


class TestGenerateCoolingTowerStl:
    @patch("filament_calibrator.cooling_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        """Parent directory is created if it doesn't exist."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = tmp_path / "nested" / "dir" / "tower.stl"
        config = CoolingTowerConfig(num_levels=5)
        result = generate_cooling_tower_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.cooling_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        """Function returns the output path for chaining."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = CoolingTowerConfig(num_levels=3)
        result = generate_cooling_tower_stl(config, output)

        assert result == output

    @patch("filament_calibrator.cooling_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        """Exports in STL format."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = CoolingTowerConfig(num_levels=3)
        generate_cooling_tower_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output

    @patch("filament_calibrator.cooling_model.cq")
    def test_calls_ensure_cq(self, mock_cq, tmp_path):
        """_ensure_cq is called before building the model."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        saved = mod.cq
        try:
            mod.cq = None
            mock_impl = MagicMock(return_value=mock_cq)
            with patch.object(mod, "_ensure_cq_impl", mock_impl):
                output = str(tmp_path / "test.stl")
                config = CoolingTowerConfig(num_levels=3)
                generate_cooling_tower_stl(config, output)

            mock_impl.assert_called_once()
        finally:
            mod.cq = saved
