"""Tests for filament_calibrator.pa_model — PA tower generation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import filament_calibrator.pa_model as mod

from filament_calibrator.pa_model import (
    LEVEL_HEIGHT,
    TOWER_DEPTH,
    TOWER_WIDTH,
    WALL_THICKNESS,
    PATowerConfig,
    _ensure_cq,
    _stub_casadi,
    generate_pa_tower_stl,
    total_height,
    _make_hollow_tower,
)


# ---------------------------------------------------------------------------
# _stub_casadi
# ---------------------------------------------------------------------------


class TestStubCasadi:
    def test_creates_stub_when_not_loaded(self):
        import sys
        import types

        saved = sys.modules.pop("casadi", None)
        saved_sub = sys.modules.pop("casadi.casadi", None)
        try:
            _stub_casadi()
            fake = sys.modules["casadi"]
            assert isinstance(fake, types.ModuleType)
            assert isinstance(sys.modules["casadi.casadi"], types.ModuleType)
            # __getattr__ returns the stub itself for any attribute access
            assert fake.Opti is fake
        finally:
            sys.modules.pop("casadi", None)
            sys.modules.pop("casadi.casadi", None)
            if saved is not None:
                sys.modules["casadi"] = saved
            if saved_sub is not None:
                sys.modules["casadi.casadi"] = saved_sub

    def test_skips_when_already_loaded(self):
        import sys

        sentinel = MagicMock()
        with patch.dict(sys.modules, {"casadi": sentinel}):
            _stub_casadi()
            assert sys.modules["casadi"] is sentinel


# ---------------------------------------------------------------------------
# _ensure_cq
# ---------------------------------------------------------------------------


class TestEnsureCq:
    def test_imports_cadquery_when_none(self):
        saved = mod.cq
        try:
            mod.cq = None
            mock_cq = MagicMock()
            with patch.dict("sys.modules", {"cadquery": mock_cq}):
                _ensure_cq()
            assert mod.cq is mock_cq
        finally:
            mod.cq = saved


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_defaults(self):
        assert TOWER_WIDTH == 60.0
        assert TOWER_DEPTH == 60.0
        assert WALL_THICKNESS == 1.6
        assert LEVEL_HEIGHT == 1.0


# ---------------------------------------------------------------------------
# PATowerConfig
# ---------------------------------------------------------------------------


class TestPATowerConfig:
    def test_defaults(self):
        config = PATowerConfig(num_levels=10)
        assert config.num_levels == 10
        assert config.level_height == LEVEL_HEIGHT
        assert config.width == TOWER_WIDTH
        assert config.depth == TOWER_DEPTH
        assert config.wall_thickness == WALL_THICKNESS
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = PATowerConfig(
            num_levels=20,
            level_height=2.0,
            width=80.0,
            depth=40.0,
            wall_thickness=2.0,
            filament_type="PETG",
        )
        assert config.num_levels == 20
        assert config.level_height == 2.0
        assert config.width == 80.0
        assert config.depth == 40.0
        assert config.wall_thickness == 2.0
        assert config.filament_type == "PETG"


# ---------------------------------------------------------------------------
# total_height
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_total_height(self):
        config = PATowerConfig(num_levels=15, level_height=1.0)
        assert total_height(config) == pytest.approx(15.0)

    def test_total_height_custom(self):
        config = PATowerConfig(num_levels=10, level_height=2.5)
        assert total_height(config) == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# _make_hollow_tower (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeHollowTower:
    @patch("filament_calibrator.pa_model.cq")
    def test_creates_outer_rect(self, mock_cq):
        """Outer rectangle is created with correct dimensions."""
        config = PATowerConfig(num_levels=10)
        height = total_height(config)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        _make_hollow_tower(config, height)

        mock_cq.Workplane.assert_any_call("XY")
        mock_wp.rect.assert_any_call(config.width, config.depth)

    @patch("filament_calibrator.pa_model.cq")
    def test_creates_inner_cutout(self, mock_cq):
        """Inner rectangle is created and cut from outer."""
        config = PATowerConfig(num_levels=10)
        height = total_height(config)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        _make_hollow_tower(config, height)

        inner_w = config.width - 2 * config.wall_thickness
        inner_d = config.depth - 2 * config.wall_thickness
        mock_wp.rect.assert_any_call(inner_w, inner_d)
        assert mock_wp.cut.call_count == 1

    @patch("filament_calibrator.pa_model.cq")
    def test_no_fillet_calls(self, mock_cq):
        """No fillets — sharp corners are the point."""
        config = PATowerConfig(num_levels=10)
        height = total_height(config)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        _make_hollow_tower(config, height)

        mock_wp.fillet.assert_not_called()


# ---------------------------------------------------------------------------
# generate_pa_tower_stl
# ---------------------------------------------------------------------------


class TestGeneratePATowerStl:
    @patch("filament_calibrator.pa_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        """Parent directory is created if it doesn't exist."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        output = tmp_path / "nested" / "dir" / "tower.stl"
        config = PATowerConfig(num_levels=5)
        result = generate_pa_tower_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.pa_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        """Function returns the output path for chaining."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = PATowerConfig(num_levels=3)
        result = generate_pa_tower_stl(config, output)

        assert result == output

    @patch("filament_calibrator.pa_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        """Exports in STL format."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = PATowerConfig(num_levels=3)
        generate_pa_tower_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output
