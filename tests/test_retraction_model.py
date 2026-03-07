"""Tests for filament_calibrator.retraction_model — two-tower retraction geometry."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from filament_calibrator.retraction_model import (
    BASE_HEIGHT,
    BASE_LENGTH,
    BASE_WIDTH,
    LEVEL_HEIGHT,
    TOWER_DIAMETER,
    TOWER_SPACING,
    RetractionTowerConfig,
    _make_base,
    _make_retraction_towers,
    _make_tower,
    generate_retraction_tower_stl,
    total_height,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_tower_diameter(self):
        assert TOWER_DIAMETER == 10.0

    def test_tower_spacing(self):
        assert TOWER_SPACING == 50.0

    def test_base_length(self):
        assert BASE_LENGTH == 70.0

    def test_base_width(self):
        assert BASE_WIDTH == 20.0

    def test_base_height(self):
        assert BASE_HEIGHT == 1.0

    def test_level_height(self):
        assert LEVEL_HEIGHT == 1.0


# ---------------------------------------------------------------------------
# RetractionTowerConfig
# ---------------------------------------------------------------------------


class TestRetractionTowerConfig:
    def test_defaults(self):
        config = RetractionTowerConfig(num_levels=10)
        assert config.num_levels == 10
        assert config.level_height == LEVEL_HEIGHT
        assert config.tower_diameter == TOWER_DIAMETER
        assert config.tower_spacing == TOWER_SPACING
        assert config.base_length == BASE_LENGTH
        assert config.base_width == BASE_WIDTH
        assert config.base_height == BASE_HEIGHT
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = RetractionTowerConfig(
            num_levels=20,
            level_height=2.0,
            tower_diameter=15.0,
            tower_spacing=60.0,
            base_length=80.0,
            base_width=25.0,
            base_height=2.0,
            filament_type="PETG",
        )
        assert config.num_levels == 20
        assert config.level_height == 2.0
        assert config.tower_diameter == 15.0
        assert config.tower_spacing == 60.0
        assert config.base_length == 80.0
        assert config.base_width == 25.0
        assert config.base_height == 2.0
        assert config.filament_type == "PETG"


# ---------------------------------------------------------------------------
# total_height
# ---------------------------------------------------------------------------


class TestTotalHeight:
    def test_default_config(self):
        config = RetractionTowerConfig(num_levels=10)
        assert total_height(config) == pytest.approx(11.0)

    def test_custom_level_height(self):
        config = RetractionTowerConfig(num_levels=5, level_height=2.0)
        assert total_height(config) == pytest.approx(11.0)

    def test_custom_base_height(self):
        config = RetractionTowerConfig(
            num_levels=10, level_height=1.0, base_height=2.0,
        )
        assert total_height(config) == pytest.approx(12.0)

    def test_single_level(self):
        config = RetractionTowerConfig(num_levels=1)
        assert total_height(config) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# _make_base (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeBase:
    @patch("filament_calibrator.retraction_model.cq")
    def test_creates_box(self, mock_cq):
        """Base plate is created as a box with correct dimensions."""
        config = RetractionTowerConfig(num_levels=5)

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
    @patch("filament_calibrator.retraction_model.cq")
    def test_creates_cylinder(self, mock_cq):
        """Tower is created as a circle extruded to height."""
        config = RetractionTowerConfig(num_levels=5)
        height = 5.0

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_tower(config, height, 25.0)

        mock_wp.circle.assert_called_once_with(config.tower_diameter / 2.0)
        mock_wp.extrude.assert_called_once_with(height)
        mock_wp.translate.assert_called_once_with(
            (25.0, 0, config.base_height),
        )

    @patch("filament_calibrator.retraction_model.cq")
    def test_negative_offset(self, mock_cq):
        """Tower can be created at negative X offset."""
        config = RetractionTowerConfig(num_levels=5)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_tower(config, 5.0, -25.0)

        mock_wp.translate.assert_called_once_with(
            (-25.0, 0, config.base_height),
        )


# ---------------------------------------------------------------------------
# _make_retraction_towers (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeRetractionTowers:
    @patch("filament_calibrator.retraction_model.cq")
    def test_creates_base_and_two_towers(self, mock_cq):
        """Model consists of a base plate and two cylindrical towers."""
        config = RetractionTowerConfig(num_levels=5)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_retraction_towers(config)

        # base + 2 towers = 3 Workplane("XY") calls
        assert mock_cq.Workplane.call_count == 3
        # Two union calls (left tower + right tower)
        assert mock_wp.union.call_count == 2


# ---------------------------------------------------------------------------
# generate_retraction_tower_stl
# ---------------------------------------------------------------------------


class TestGenerateRetractionTowerStl:
    @patch("filament_calibrator.retraction_model.cq")
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
        config = RetractionTowerConfig(num_levels=5)
        result = generate_retraction_tower_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.retraction_model.cq")
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
        config = RetractionTowerConfig(num_levels=3)
        result = generate_retraction_tower_stl(config, output)

        assert result == output

    @patch("filament_calibrator.retraction_model.cq")
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
        config = RetractionTowerConfig(num_levels=3)
        generate_retraction_tower_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output
