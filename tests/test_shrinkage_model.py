"""Tests for filament_calibrator.shrinkage_model — shrinkage cross generation."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import filament_calibrator.shrinkage_model as mod

from filament_calibrator.shrinkage_model import (
    ARM_LENGTH,
    ARM_SIZE,
    LABEL_DEPTH,
    LABEL_FONT_SIZE,
    WINDOW_INTERVAL,
    WINDOW_SIZE,
    ShrinkageCrossConfig,
    _ensure_cq,
    _make_cross,
    _window_positions,
    generate_shrinkage_cross_stl,
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
        assert ARM_LENGTH == 100.0
        assert ARM_SIZE == 10.0
        assert WINDOW_SIZE == 5.0
        assert WINDOW_INTERVAL == 20.0
        assert LABEL_DEPTH == 0.6
        assert LABEL_FONT_SIZE == 6.0


# ---------------------------------------------------------------------------
# ShrinkageCrossConfig
# ---------------------------------------------------------------------------


class TestShrinkageCrossConfig:
    def test_defaults(self):
        config = ShrinkageCrossConfig()
        assert config.arm_length == ARM_LENGTH
        assert config.arm_size == ARM_SIZE
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = ShrinkageCrossConfig(
            arm_length=80.0, arm_size=8.0, filament_type="ABS",
        )
        assert config.arm_length == 80.0
        assert config.arm_size == 8.0
        assert config.filament_type == "ABS"


# ---------------------------------------------------------------------------
# _window_positions
# ---------------------------------------------------------------------------


class TestWindowPositions:
    def test_default_geometry(self):
        """Windows at 20mm intervals, skipping centre block."""
        positions = _window_positions(100.0, 20.0, 45.0, 55.0)
        assert positions == [20.0, 40.0, 60.0, 80.0]

    def test_skips_centre(self):
        """Position exactly inside centre is excluded."""
        positions = _window_positions(100.0, 10.0, 45.0, 55.0)
        # 10, 20, 30, 40 are before centre; 50 is inside; 60..90 after
        assert 50.0 not in positions
        assert 45.0 not in positions
        assert 40.0 in positions
        assert 60.0 in positions

    def test_short_arm(self):
        """Arm too short for any windows returns empty list."""
        positions = _window_positions(15.0, 20.0, 2.5, 12.5)
        assert positions == []

    def test_no_centre_overlap(self):
        """All positions outside centre when arm is long enough."""
        positions = _window_positions(200.0, 20.0, 95.0, 105.0)
        for p in positions:
            assert p < 95.0 or p > 105.0


# ---------------------------------------------------------------------------
# _make_cross (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeCross:
    @patch("filament_calibrator.shrinkage_model.cq")
    def test_creates_three_arms(self, mock_cq):
        """Three boxes are created for X, Y, and Z arms."""
        config = ShrinkageCrossConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cross(config)

        # Three box() calls for the three arms
        box_calls = mock_wp.box.call_args_list
        assert len(box_calls) == 3

    @patch("filament_calibrator.shrinkage_model.cq")
    def test_x_arm_dimensions(self, mock_cq):
        """X arm has correct dimensions."""
        config = ShrinkageCrossConfig(arm_length=100.0, arm_size=10.0)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cross(config)

        # First box call is the X arm
        first_box = mock_wp.box.call_args_list[0]
        assert first_box == call(100.0, 10.0, 10.0, centered=False)

    @patch("filament_calibrator.shrinkage_model.cq")
    def test_window_cutouts(self, mock_cq):
        """Window cutouts are created via cut()."""
        config = ShrinkageCrossConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cross(config)

        # cut() must be called (windows on X, Y, and Z arms)
        assert mock_wp.cut.call_count > 0

    @patch("filament_calibrator.shrinkage_model.cq")
    def test_axis_labels(self, mock_cq):
        """X, Y, and Z text labels are created."""
        config = ShrinkageCrossConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cross(config)

        # Three text() calls for X, Y, Z labels
        text_calls = mock_wp.text.call_args_list
        assert len(text_calls) == 3
        labels = {c[0][0] for c in text_calls}
        assert labels == {"X", "Y", "Z"}

    @patch("filament_calibrator.shrinkage_model.cq")
    def test_custom_arm_length(self, mock_cq):
        """Custom arm length is propagated to box dimensions."""
        config = ShrinkageCrossConfig(arm_length=80.0, arm_size=8.0)

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        _make_cross(config)

        first_box = mock_wp.box.call_args_list[0]
        assert first_box == call(80.0, 8.0, 8.0, centered=False)


# ---------------------------------------------------------------------------
# generate_shrinkage_cross_stl
# ---------------------------------------------------------------------------


class TestGenerateShrinkageCrossStl:
    @patch("filament_calibrator.shrinkage_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        """Parent directory is created if it doesn't exist."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        output = tmp_path / "nested" / "dir" / "cross.stl"
        config = ShrinkageCrossConfig()
        result = generate_shrinkage_cross_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.shrinkage_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        """Function returns the output path for chaining."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = ShrinkageCrossConfig()
        result = generate_shrinkage_cross_stl(config, output)

        assert result == output

    @patch("filament_calibrator.shrinkage_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        """Exports in STL format."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.transformed.return_value = mock_wp
        mock_wp.union.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.workplane.return_value = mock_wp
        mock_wp.center.return_value = mock_wp
        mock_wp.text.return_value = mock_wp
        mock_wp.rect.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = ShrinkageCrossConfig()
        generate_shrinkage_cross_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output
