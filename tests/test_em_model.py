"""Tests for filament_calibrator.em_model — EM cube generation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import filament_calibrator.em_model as mod

from filament_calibrator.em_model import (
    CUBE_SIZE,
    EMCubeConfig,
    _ensure_cq,
    _stub_casadi,
    _make_cube,
    generate_em_cube_stl,
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
            assert isinstance(sys.modules["casadi"], types.ModuleType)
            assert isinstance(sys.modules["casadi.casadi"], types.ModuleType)
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
        assert CUBE_SIZE == 40.0


# ---------------------------------------------------------------------------
# EMCubeConfig
# ---------------------------------------------------------------------------


class TestEMCubeConfig:
    def test_defaults(self):
        config = EMCubeConfig()
        assert config.size == CUBE_SIZE
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = EMCubeConfig(size=30.0, filament_type="PETG")
        assert config.size == 30.0
        assert config.filament_type == "PETG"


# ---------------------------------------------------------------------------
# _make_cube (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeCube:
    @patch("filament_calibrator.em_model.cq")
    def test_creates_rect(self, mock_cq):
        """Rectangle is created with correct dimensions."""
        config = EMCubeConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cube(config)

        mock_cq.Workplane.assert_called_once_with("XY")
        mock_wp.rect.assert_called_once_with(config.size, config.size)

    @patch("filament_calibrator.em_model.cq")
    def test_extrudes_to_cube_height(self, mock_cq):
        """Cube is extruded to the correct height."""
        config = EMCubeConfig(size=30.0)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cube(config)

        mock_wp.extrude.assert_called_once_with(30.0)

    @patch("filament_calibrator.em_model.cq")
    def test_no_cut_or_fillet(self, mock_cq):
        """No cut or fillet — solid cube for vase-mode slicing."""
        config = EMCubeConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cube(config)

        mock_wp.cut.assert_not_called()
        mock_wp.fillet.assert_not_called()


# ---------------------------------------------------------------------------
# generate_em_cube_stl
# ---------------------------------------------------------------------------


class TestGenerateEmCubeStl:
    @patch("filament_calibrator.em_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        """Parent directory is created if it doesn't exist."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        output = tmp_path / "nested" / "dir" / "cube.stl"
        config = EMCubeConfig()
        result = generate_em_cube_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.em_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        """Function returns the output path for chaining."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = EMCubeConfig()
        result = generate_em_cube_stl(config, output)

        assert result == output

    @patch("filament_calibrator.em_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        """Exports in STL format."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = EMCubeConfig()
        generate_em_cube_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output
