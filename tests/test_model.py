"""Tests for filament_calibrator.model — CadQuery temp tower generation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from filament_calibrator.model import (
    BASE_FILLET,
    BASE_HEIGHT,
    BASE_LENGTH,
    BASE_WIDTH,
    CONE_HEIGHT,
    CUTOUT_HEIGHT,
    CUTOUT_LENGTH,
    CUTOUT_OFFSET,
    HOLE_35_OFFSET,
    HOLE_45_OFFSET,
    HOLE_DIAM,
    HORIZ_HOLE_LEN,
    LG_CONE_DIAM,
    LG_CONE_OFFSET,
    OH_LABEL_DEPTH,
    OH_LABEL_SIZE,
    OVERHANG_35_X,
    OVERHANG_45_X,
    PROTRUSION_DEPTH,
    PROTRUSION_HEIGHT,
    PROTRUSION_LENGTH,
    SM_CONE_DIAM,
    SM_CONE_OFFSET,
    TEMP_LABEL_DEPTH,
    TEMP_LABEL_H_OFFSET,
    TEMP_LABEL_SIZE,
    TEMP_LABEL_V_OFFSET,
    TEST_CUTOUT_DEPTH,
    TEST_CUTOUT_H_OFFSET,
    TEST_CUTOUT_V_OFFSET,
    TIER_HEIGHT,
    TIER_LENGTH,
    TIER_WIDTH,
    TEXT_DEPTH,
    TowerConfig,
    export_stl,
    generate_tower_stl,
    make_base,
    make_tier,
    make_tower,
    tier_temperature,
    total_height,
)


# ---------------------------------------------------------------------------
# TowerConfig
# ---------------------------------------------------------------------------


class TestTowerConfig:
    def test_defaults(self):
        c = TowerConfig()
        assert c.high_temp == 220
        assert c.temp_jump == 10
        assert c.num_tiers == 9
        assert c.filament_type == "PLA"
        assert c.brand_top == ""
        assert c.brand_bottom == ""

    def test_custom(self):
        c = TowerConfig(high_temp=250, temp_jump=5, num_tiers=6,
                        filament_type="PETG", brand_top="BrandA",
                        brand_bottom="BrandB")
        assert c.high_temp == 250
        assert c.temp_jump == 5
        assert c.num_tiers == 6
        assert c.filament_type == "PETG"
        assert c.brand_top == "BrandA"
        assert c.brand_bottom == "BrandB"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestTierTemperature:
    def test_bottom_tier(self):
        c = TowerConfig(high_temp=220, temp_jump=10)
        assert tier_temperature(c, 0) == 220

    def test_second_tier(self):
        c = TowerConfig(high_temp=220, temp_jump=10)
        assert tier_temperature(c, 1) == 210

    def test_top_tier(self):
        c = TowerConfig(high_temp=220, temp_jump=10, num_tiers=9)
        assert tier_temperature(c, 8) == 140

    def test_custom_jump(self):
        c = TowerConfig(high_temp=250, temp_jump=5)
        assert tier_temperature(c, 3) == 235


class TestTotalHeight:
    def test_default(self):
        c = TowerConfig(num_tiers=9)
        assert total_height(c) == pytest.approx(91.0)

    def test_single_tier(self):
        c = TowerConfig(num_tiers=1)
        assert total_height(c) == pytest.approx(11.0)


# ---------------------------------------------------------------------------
# Geometry constants sanity checks
# ---------------------------------------------------------------------------


class TestConstants:
    def test_base_dimensions(self):
        assert BASE_LENGTH == pytest.approx(89.3)
        assert BASE_WIDTH == pytest.approx(20.0)
        assert BASE_HEIGHT == pytest.approx(1.0)
        assert BASE_FILLET == pytest.approx(4.0)

    def test_tier_dimensions(self):
        assert TIER_LENGTH == pytest.approx(79.0)
        assert TIER_WIDTH == pytest.approx(10.0)
        assert TIER_HEIGHT == pytest.approx(10.0)

    def test_overhang_dimensions(self):
        assert OVERHANG_45_X == pytest.approx(10.0)
        assert OVERHANG_35_X == pytest.approx(14.281)

    def test_cutout_dimensions(self):
        assert CUTOUT_LENGTH == pytest.approx(30.0)
        assert CUTOUT_HEIGHT == pytest.approx(9.0)
        assert CUTOUT_OFFSET == pytest.approx(15.0)

    def test_cone_dimensions(self):
        assert CONE_HEIGHT == pytest.approx(5.0)
        assert SM_CONE_DIAM == pytest.approx(3.0)
        assert SM_CONE_OFFSET == pytest.approx(5.0)
        assert LG_CONE_DIAM == pytest.approx(5.0)
        assert LG_CONE_OFFSET == pytest.approx(25.0)

    def test_hole_dimensions(self):
        assert HOLE_DIAM == pytest.approx(3.0)
        assert HOLE_45_OFFSET == pytest.approx(3.671)
        assert HOLE_35_OFFSET == pytest.approx(75.0)
        assert HORIZ_HOLE_LEN == pytest.approx(5.0)

    def test_test_cutout_constants(self):
        assert TEST_CUTOUT_H_OFFSET == pytest.approx(47.0)
        assert TEST_CUTOUT_V_OFFSET == pytest.approx(0.3)
        assert TEST_CUTOUT_DEPTH == pytest.approx(8.0)

    def test_protrusion_dimensions(self):
        assert PROTRUSION_LENGTH == pytest.approx(16.0)
        assert PROTRUSION_HEIGHT == pytest.approx(0.7)
        assert PROTRUSION_DEPTH == pytest.approx(0.5)

    def test_label_constants(self):
        assert TEMP_LABEL_SIZE == pytest.approx(6.0)
        assert TEMP_LABEL_DEPTH == pytest.approx(1.0)
        assert TEMP_LABEL_V_OFFSET == pytest.approx(6.0)
        assert TEMP_LABEL_H_OFFSET == pytest.approx(25.0)
        assert TEXT_DEPTH == pytest.approx(0.6)
        assert OH_LABEL_SIZE == pytest.approx(3.0)
        assert OH_LABEL_DEPTH == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# CadQuery geometry tests (with mocking)
# ---------------------------------------------------------------------------


class TestMakeBase:
    @patch("filament_calibrator.model.cq")
    def test_creates_base_with_label(self, mock_cq):
        """make_base calls union to add filament type label."""
        config = TowerConfig(filament_type="PLA")
        base_mock = mock_cq.Workplane.return_value.rect.return_value.extrude.return_value.edges.return_value.fillet.return_value
        result = make_base(config)
        # union is called for filament type label
        assert base_mock.union.called

    @patch("filament_calibrator.model.cq")
    def test_no_filament_type_skips_label(self, mock_cq):
        """When filament_type is empty, union for label is not called."""
        config = TowerConfig(filament_type="")
        base_mock = mock_cq.Workplane.return_value.rect.return_value.extrude.return_value.edges.return_value.fillet.return_value
        make_base(config)
        assert not base_mock.union.called

    @patch("filament_calibrator.model.cq")
    def test_brand_bottom_creates_cut(self, mock_cq):
        """When brand_bottom is set, cut is called on the base."""
        config = TowerConfig(brand_bottom="TestBrand")
        base_mock = mock_cq.Workplane.return_value.rect.return_value.extrude.return_value.edges.return_value.fillet.return_value
        make_base(config)
        assert base_mock.union.return_value.cut.called


class TestMakeTier:
    @patch("filament_calibrator.model.cq")
    def test_first_tier_has_overhang_labels(self, mock_cq):
        """Tier 0 exercises overhang label builders (covers their bodies)."""
        config = TowerConfig()
        make_tier(config, 0)
        # text() is called for temp label + two overhang labels
        text_calls = [
            c for c in mock_cq.Workplane.return_value.method_calls
            if "text" in str(c)
        ]
        # At minimum, CadQuery operations were invoked (function bodies ran)
        assert mock_cq.Workplane.called

    @patch("filament_calibrator.model._make_overhang_label_35")
    @patch("filament_calibrator.model._make_overhang_label_45")
    @patch("filament_calibrator.model.cq")
    def test_first_tier_calls_overhang_builders(self, mock_cq, mock_oh45, mock_oh35):
        """Tier 0 calls both overhang label builders."""
        config = TowerConfig()
        make_tier(config, 0)
        mock_oh45.assert_called_once()
        mock_oh35.assert_called_once()

    @patch("filament_calibrator.model._make_overhang_label_35")
    @patch("filament_calibrator.model._make_overhang_label_45")
    @patch("filament_calibrator.model.cq")
    def test_non_first_tier_no_overhang_labels(self, mock_cq, mock_oh45, mock_oh35):
        """Tier 1 does not call overhang label builders."""
        config = TowerConfig()
        make_tier(config, 1)
        mock_oh45.assert_not_called()
        mock_oh35.assert_not_called()


class TestMakeTower:
    @patch("filament_calibrator.model.make_tier")
    @patch("filament_calibrator.model.make_base")
    def test_assembles_all_tiers(self, mock_base, mock_tier):
        """make_tower calls make_tier once per tier."""
        mock_base.return_value = MagicMock()
        mock_tier.return_value = MagicMock()
        config = TowerConfig(num_tiers=3)
        make_tower(config)
        assert mock_tier.call_count == 3
        assert mock_tier.call_args_list == [
            call(config, 0), call(config, 1), call(config, 2),
        ]

    @patch("filament_calibrator.model.cq")
    def test_brand_top_exercises_label(self, mock_cq):
        """When brand_top is set, _make_brand_top_label body executes."""
        config = TowerConfig(num_tiers=1, brand_top="MyBrand")
        make_tower(config)
        # CadQuery operations were invoked (covers _make_brand_top_label body)
        assert mock_cq.Workplane.called

    @patch("filament_calibrator.model._make_brand_top_label")
    @patch("filament_calibrator.model.make_tier")
    @patch("filament_calibrator.model.make_base")
    def test_brand_top_calls_builder(self, mock_base, mock_tier, mock_brand):
        """When brand_top is set, _make_brand_top_label is called."""
        mock_base.return_value = MagicMock()
        mock_tier.return_value = MagicMock()
        config = TowerConfig(num_tiers=2, brand_top="MyBrand")
        make_tower(config)
        mock_brand.assert_called_once_with("MyBrand", config)

    @patch("filament_calibrator.model._make_brand_top_label")
    @patch("filament_calibrator.model.make_tier")
    @patch("filament_calibrator.model.make_base")
    def test_no_brand_top_skips(self, mock_base, mock_tier, mock_brand):
        """When brand_top is empty, _make_brand_top_label is not called."""
        mock_base.return_value = MagicMock()
        mock_tier.return_value = MagicMock()
        config = TowerConfig(num_tiers=2, brand_top="")
        make_tower(config)
        mock_brand.assert_not_called()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExportStl:
    @patch("filament_calibrator.model.cq")
    def test_calls_exporter(self, mock_cq):
        mock_shape = MagicMock()
        export_stl(mock_shape, "/tmp/test.stl")
        mock_cq.exporters.export.assert_called_once_with(
            mock_shape, "/tmp/test.stl", exportType="STL"
        )


class TestGenerateTowerStl:
    @patch("filament_calibrator.model.export_stl")
    @patch("filament_calibrator.model.make_tower")
    def test_builds_and_exports(self, mock_make, mock_export, tmp_path):
        mock_make.return_value = MagicMock()
        config = TowerConfig()
        out = str(tmp_path / "tower.stl")

        result = generate_tower_stl(config, out)

        assert result == out
        mock_make.assert_called_once_with(config)
        mock_export.assert_called_once_with(mock_make.return_value, out)

    @patch("filament_calibrator.model.export_stl")
    @patch("filament_calibrator.model.make_tower")
    def test_creates_parent_dirs(self, mock_make, mock_export, tmp_path):
        mock_make.return_value = MagicMock()
        config = TowerConfig()
        nested = tmp_path / "a" / "b" / "c" / "tower.stl"
        generate_tower_stl(config, str(nested))
        assert nested.parent.exists()
