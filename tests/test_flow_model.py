"""Tests for filament_calibrator.flow_model — serpentine specimen generation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

import filament_calibrator.flow_model as mod

from filament_calibrator.flow_model import (
    ARM_THICKNESS,
    GAP_WIDTH,
    LEVEL_HEIGHT,
    NUM_ARMS,
    SPECIMEN_WIDTH,
    FlowSpecimenConfig,
    _ensure_cq,
    _stub_casadi,
    generate_flow_specimen_stl,
    specimen_depth,
    total_height,
    _make_serpentine,
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
        assert SPECIMEN_WIDTH == 170.0
        assert ARM_THICKNESS == 20.0
        assert GAP_WIDTH == 20.0
        assert NUM_ARMS == 3
        assert LEVEL_HEIGHT == 1.0


# ---------------------------------------------------------------------------
# FlowSpecimenConfig
# ---------------------------------------------------------------------------


class TestFlowSpecimenConfig:
    def test_defaults(self):
        config = FlowSpecimenConfig(num_levels=10)
        assert config.num_levels == 10
        assert config.level_height == LEVEL_HEIGHT
        assert config.width == SPECIMEN_WIDTH
        assert config.arm_thickness == ARM_THICKNESS
        assert config.gap_width == GAP_WIDTH
        assert config.num_arms == NUM_ARMS
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = FlowSpecimenConfig(
            num_levels=20,
            level_height=2.0,
            width=100.0,
            arm_thickness=15.0,
            gap_width=10.0,
            num_arms=4,
            filament_type="PETG",
        )
        assert config.num_levels == 20
        assert config.level_height == 2.0
        assert config.width == 100.0
        assert config.arm_thickness == 15.0
        assert config.gap_width == 10.0
        assert config.num_arms == 4
        assert config.filament_type == "PETG"


# ---------------------------------------------------------------------------
# specimen_depth / total_height
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_specimen_depth_default(self):
        config = FlowSpecimenConfig(num_levels=10)
        # 3 * 20 + 2 * 20 = 100
        assert specimen_depth(config) == pytest.approx(100.0)

    def test_specimen_depth_custom(self):
        config = FlowSpecimenConfig(
            num_levels=10,
            arm_thickness=10.0,
            gap_width=5.0,
            num_arms=4,
        )
        # 4 * 10 + 3 * 5 = 55
        assert specimen_depth(config) == pytest.approx(55.0)

    def test_total_height(self):
        config = FlowSpecimenConfig(num_levels=15, level_height=1.0)
        assert total_height(config) == pytest.approx(15.0)

    def test_total_height_custom(self):
        config = FlowSpecimenConfig(num_levels=10, level_height=2.5)
        assert total_height(config) == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# _make_serpentine (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeSerpentine:
    @patch("filament_calibrator.flow_model.cq")
    def test_creates_bounding_rect(self, mock_cq):
        """Full bounding rectangle is created with correct dimensions."""
        config = FlowSpecimenConfig(num_levels=10)
        depth = specimen_depth(config)
        height = total_height(config)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.edges.return_value = mock_wp
        mock_wp.fillet.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_cq.Vector = MagicMock()

        _make_serpentine(config, height)

        # First Workplane call creates the bounding rectangle
        mock_cq.Workplane.assert_any_call("XY")
        mock_wp.rect.assert_any_call(config.width, depth)

    @patch("filament_calibrator.flow_model.cq")
    def test_cuts_correct_number_of_slots(self, mock_cq):
        """Two slots are cut for 3 arms."""
        config = FlowSpecimenConfig(num_levels=10, num_arms=3)
        height = total_height(config)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.edges.return_value = mock_wp
        mock_wp.fillet.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_cq.Vector = MagicMock()

        _make_serpentine(config, height)

        # num_arms - 1 = 2 cuts
        assert mock_wp.cut.call_count == 2

    @patch("filament_calibrator.flow_model.cq")
    def test_cuts_four_slots_for_five_arms(self, mock_cq):
        """Four slots are cut for 5 arms."""
        config = FlowSpecimenConfig(num_levels=10, num_arms=5)
        height = total_height(config)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.edges.return_value = mock_wp
        mock_wp.fillet.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_cq.Vector = MagicMock()

        _make_serpentine(config, height)

        assert mock_wp.cut.call_count == 4

    @patch("filament_calibrator.flow_model.cq")
    def test_fillets_vertical_edges_three_passes(self, mock_cq):
        """Vertical edges are filleted in 3 passes with two radii."""
        config = FlowSpecimenConfig(num_levels=10)
        height = total_height(config)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.edges.return_value = mock_wp
        mock_wp.fillet.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_cq.Vector = MagicMock()
        mock_cq.selectors.BoxSelector = MagicMock()

        _make_serpentine(config, height)

        # Three fillet passes: inner gap, right outer, left spine
        assert mock_wp.fillet.call_count == 3
        inner_r = GAP_WIDTH / 2 - 0.01
        outer_r = ARM_THICKNESS / 2 - 0.01
        spine_r = ARM_THICKNESS - 0.5
        fillet_radii = [c[0][0] for c in mock_wp.fillet.call_args_list]
        assert fillet_radii[0] == pytest.approx(inner_r)
        assert fillet_radii[1] == pytest.approx(outer_r)
        assert fillet_radii[2] == pytest.approx(spine_r)

        # edges("|Z") called once per pass
        z_calls = [c for c in mock_wp.edges.call_args_list if c == call("|Z")]
        assert len(z_calls) == 3

        # BoxSelector called 3 times for position-based selection
        assert mock_cq.selectors.BoxSelector.call_count == 3


# ---------------------------------------------------------------------------
# generate_flow_specimen_stl
# ---------------------------------------------------------------------------


class TestGenerateFlowSpecimenStl:
    @patch("filament_calibrator.flow_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        """Parent directory is created if it doesn't exist."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.edges.return_value = mock_wp
        mock_wp.fillet.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_cq.Vector = MagicMock()

        output = tmp_path / "nested" / "dir" / "specimen.stl"
        config = FlowSpecimenConfig(num_levels=5)
        result = generate_flow_specimen_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.flow_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        """Function returns the output path for chaining."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.edges.return_value = mock_wp
        mock_wp.fillet.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_cq.Vector = MagicMock()

        output = str(tmp_path / "test.stl")
        config = FlowSpecimenConfig(num_levels=3)
        result = generate_flow_specimen_stl(config, output)

        assert result == output

    @patch("filament_calibrator.flow_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        """Exports in STL format."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.edges.return_value = mock_wp
        mock_wp.fillet.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_cq.Vector = MagicMock()

        output = str(tmp_path / "test.stl")
        config = FlowSpecimenConfig(num_levels=3)
        generate_flow_specimen_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output
