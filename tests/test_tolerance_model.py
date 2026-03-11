"""Tests for filament_calibrator.tolerance_model -- tolerance test generation."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import filament_calibrator.tolerance_model as mod

from filament_calibrator.tolerance_model import (
    BASE_HEIGHT,
    COLUMN_SPACING,
    DEFAULT_DIAMETERS,
    PEG_BASE_HEIGHT,
    PEG_HEIGHT,
    PLATE_MARGIN,
    PLATE_THICKNESS,
    ROW_SPACING,
    ToleranceTestConfig,
    _ensure_cq,
    _hole_positions_x,
    _make_hole_plate,
    _make_peg,
    _make_peg_row,
    _make_tolerance_test,
    generate_tolerance_stl,
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
        assert PLATE_THICKNESS == 5.0
        assert PEG_HEIGHT == 10.0
        assert PEG_BASE_HEIGHT == 2.0
        assert COLUMN_SPACING == 20.0
        assert ROW_SPACING == 25.0
        assert PLATE_MARGIN == 5.0
        assert BASE_HEIGHT == 1.0
        assert DEFAULT_DIAMETERS == (3.0, 5.0, 8.0, 10.0, 12.0, 15.0)


# ---------------------------------------------------------------------------
# ToleranceTestConfig
# ---------------------------------------------------------------------------


class TestToleranceTestConfig:
    def test_defaults(self):
        config = ToleranceTestConfig()
        assert config.diameters == DEFAULT_DIAMETERS
        assert config.plate_thickness == PLATE_THICKNESS
        assert config.peg_height == PEG_HEIGHT
        assert config.peg_base_height == PEG_BASE_HEIGHT
        assert config.column_spacing == COLUMN_SPACING
        assert config.row_spacing == ROW_SPACING
        assert config.plate_margin == PLATE_MARGIN
        assert config.base_height == BASE_HEIGHT
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = ToleranceTestConfig(
            diameters=(4.0, 6.0),
            plate_thickness=8.0,
            peg_height=15.0,
            peg_base_height=3.0,
            column_spacing=25.0,
            row_spacing=30.0,
            plate_margin=8.0,
            base_height=2.0,
            filament_type="ABS",
        )
        assert config.diameters == (4.0, 6.0)
        assert config.plate_thickness == 8.0
        assert config.peg_height == 15.0
        assert config.peg_base_height == 3.0
        assert config.column_spacing == 25.0
        assert config.row_spacing == 30.0
        assert config.plate_margin == 8.0
        assert config.base_height == 2.0
        assert config.filament_type == "ABS"


# ---------------------------------------------------------------------------
# total_width
# ---------------------------------------------------------------------------


class TestTotalWidth:
    def test_default_config(self):
        config = ToleranceTestConfig()
        n = len(config.diameters)
        max_d = max(config.diameters)
        expected = (n - 1) * config.column_spacing + max_d + 2 * config.plate_margin
        assert total_width(config) == expected

    def test_single_diameter(self):
        config = ToleranceTestConfig(diameters=(10.0,))
        expected = 0 * config.column_spacing + 10.0 + 2 * config.plate_margin
        assert total_width(config) == expected


# ---------------------------------------------------------------------------
# total_depth
# ---------------------------------------------------------------------------


class TestTotalDepth:
    def test_default_config(self):
        config = ToleranceTestConfig()
        max_d = max(config.diameters)
        expected = config.row_spacing + max_d + 2 * config.plate_margin
        assert total_depth(config) == expected

    def test_custom_config(self):
        config = ToleranceTestConfig(row_spacing=30.0, diameters=(8.0,))
        expected = 30.0 + 8.0 + 2 * config.plate_margin
        assert total_depth(config) == expected


# ---------------------------------------------------------------------------
# _hole_positions_x
# ---------------------------------------------------------------------------


class TestHolePositionsX:
    def test_default_config(self):
        config = ToleranceTestConfig()
        positions = _hole_positions_x(config)
        n = len(config.diameters)
        assert len(positions) == n
        # Centred around 0
        total_span = (n - 1) * config.column_spacing
        assert positions[0] == -total_span / 2.0
        assert positions[-1] == total_span / 2.0

    def test_single_diameter(self):
        config = ToleranceTestConfig(diameters=(10.0,))
        positions = _hole_positions_x(config)
        assert positions == [0.0]

    def test_two_diameters(self):
        config = ToleranceTestConfig(diameters=(5.0, 10.0), column_spacing=20.0)
        positions = _hole_positions_x(config)
        assert positions == [-10.0, 10.0]


# ---------------------------------------------------------------------------
# _make_hole_plate (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeHolePlate:
    @patch("filament_calibrator.tolerance_model.cq")
    def test_creates_plate_and_cuts_holes(self, mock_cq):
        config = ToleranceTestConfig(diameters=(5.0, 10.0))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        _make_hole_plate(config)

        # 2 holes cut
        assert mock_wp.cut.call_count == 2

    @patch("filament_calibrator.tolerance_model.cq")
    def test_circle_radii(self, mock_cq):
        config = ToleranceTestConfig(diameters=(6.0, 12.0))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp

        _make_hole_plate(config)

        circle_calls = mock_wp.circle.call_args_list
        radii = [c[0][0] for c in circle_calls]
        assert 3.0 in radii
        assert 6.0 in radii


# ---------------------------------------------------------------------------
# _make_peg (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakePeg:
    @patch("filament_calibrator.tolerance_model.cq")
    def test_creates_cylinder_and_translates(self, mock_cq):
        config = ToleranceTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_peg(config, 8.0, 10.0, -5.0)

        mock_wp.circle.assert_called_once_with(4.0)
        mock_wp.extrude.assert_called_once_with(config.peg_height)
        z_bottom = config.base_height + config.peg_base_height
        mock_wp.translate.assert_called_once_with((10.0, -5.0, z_bottom))


# ---------------------------------------------------------------------------
# _make_peg_row (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakePegRow:
    @patch("filament_calibrator.tolerance_model.cq")
    def test_creates_base_and_unions_pegs(self, mock_cq):
        config = ToleranceTestConfig(diameters=(5.0, 10.0))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_peg_row(config)

        # 2 pegs union'd
        assert mock_wp.union.call_count == 2


# ---------------------------------------------------------------------------
# _make_tolerance_test (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeToleranceTest:
    @patch("filament_calibrator.tolerance_model.cq")
    def test_unions_plate_and_peg_row(self, mock_cq):
        config = ToleranceTestConfig(diameters=(5.0, 10.0))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_tolerance_test(config)

        # At minimum: hole_plate union + peg_row union + peg unions inside peg_row
        assert mock_wp.union.call_count >= 2


# ---------------------------------------------------------------------------
# generate_tolerance_stl
# ---------------------------------------------------------------------------


class TestGenerateToleranceStl:
    @patch("filament_calibrator.tolerance_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = tmp_path / "nested" / "dir" / "tolerance.stl"
        config = ToleranceTestConfig()
        result = generate_tolerance_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.tolerance_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = ToleranceTestConfig()
        result = generate_tolerance_stl(config, output)

        assert result == output

    @patch("filament_calibrator.tolerance_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.circle.return_value = mock_wp
        mock_wp.extrude.return_value = mock_wp
        mock_wp.cut.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = ToleranceTestConfig()
        generate_tolerance_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output
