"""Tests for filament_calibrator.bridge_model -- bridge test generation."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import filament_calibrator.bridge_model as mod

from filament_calibrator.bridge_model import (
    BASE_HEIGHT,
    BASE_MARGIN,
    BRIDGE_THICKNESS,
    DEFAULT_SPANS,
    PILLAR_DEPTH,
    PILLAR_HEIGHT,
    PILLAR_WIDTH,
    BridgeTestConfig,
    _ensure_cq,
    _make_base,
    _make_bridge,
    _make_bridge_test,
    _make_pillar,
    _pair_width,
    _total_pairs_width,
    generate_bridge_stl,
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
    def test_defaults(self):
        assert PILLAR_WIDTH == 5.0
        assert PILLAR_DEPTH == 10.0
        assert PILLAR_HEIGHT == 15.0
        assert BRIDGE_THICKNESS == 2.0
        assert BASE_HEIGHT == 1.0
        assert BASE_MARGIN == 5.0
        assert DEFAULT_SPANS == (10.0, 20.0, 30.0, 40.0, 50.0, 60.0)


# ---------------------------------------------------------------------------
# BridgeTestConfig
# ---------------------------------------------------------------------------


class TestBridgeTestConfig:
    def test_defaults(self):
        config = BridgeTestConfig()
        assert config.spans == DEFAULT_SPANS
        assert config.pillar_width == PILLAR_WIDTH
        assert config.pillar_depth == PILLAR_DEPTH
        assert config.pillar_height == PILLAR_HEIGHT
        assert config.bridge_thickness == BRIDGE_THICKNESS
        assert config.base_height == BASE_HEIGHT
        assert config.base_margin == BASE_MARGIN
        assert config.filament_type == "PLA"

    def test_custom_values(self):
        config = BridgeTestConfig(
            spans=(5.0, 15.0),
            pillar_width=8.0,
            pillar_depth=12.0,
            pillar_height=20.0,
            bridge_thickness=3.0,
            base_height=2.0,
            base_margin=8.0,
            filament_type="ABS",
        )
        assert config.spans == (5.0, 15.0)
        assert config.pillar_width == 8.0
        assert config.pillar_depth == 12.0
        assert config.pillar_height == 20.0
        assert config.bridge_thickness == 3.0
        assert config.base_height == 2.0
        assert config.base_margin == 8.0
        assert config.filament_type == "ABS"


# ---------------------------------------------------------------------------
# total_height
# ---------------------------------------------------------------------------


class TestTotalHeight:
    def test_default_config(self):
        config = BridgeTestConfig()
        assert total_height(config) == BASE_HEIGHT + PILLAR_HEIGHT + BRIDGE_THICKNESS

    def test_custom_config(self):
        config = BridgeTestConfig(base_height=2.0, pillar_height=20.0, bridge_thickness=3.0)
        assert total_height(config) == 25.0


# ---------------------------------------------------------------------------
# _pair_width
# ---------------------------------------------------------------------------


class TestPairWidth:
    def test_default_pillar_width(self):
        config = BridgeTestConfig()
        assert _pair_width(config, 30.0) == 30.0 + 2 * PILLAR_WIDTH

    def test_custom_pillar_width(self):
        config = BridgeTestConfig(pillar_width=8.0)
        assert _pair_width(config, 20.0) == 20.0 + 16.0


# ---------------------------------------------------------------------------
# _total_pairs_width
# ---------------------------------------------------------------------------


class TestTotalPairsWidth:
    def test_default_config(self):
        config = BridgeTestConfig()
        pair_widths = sum(_pair_width(config, s) for s in config.spans)
        num_gaps = len(config.spans) - 1
        expected = pair_widths + num_gaps * config.pillar_width
        assert _total_pairs_width(config) == expected

    def test_single_span(self):
        config = BridgeTestConfig(spans=(10.0,))
        # Single pair, no inter-pair gaps
        assert _total_pairs_width(config) == 10.0 + 2 * PILLAR_WIDTH


# ---------------------------------------------------------------------------
# _make_base (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeBase:
    @patch("filament_calibrator.bridge_model.cq")
    def test_creates_base_box(self, mock_cq):
        config = BridgeTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp

        _make_base(config)

        mock_cq.Workplane.assert_called_once_with("XY")
        box_call = mock_wp.box.call_args
        total_x = _total_pairs_width(config) + 2 * config.base_margin
        total_y = config.pillar_depth + 2 * config.base_margin
        assert box_call == call(
            total_x, total_y, config.base_height,
            centered=(True, True, False),
        )


# ---------------------------------------------------------------------------
# _make_pillar (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakePillar:
    @patch("filament_calibrator.bridge_model.cq")
    def test_creates_pillar_box_and_translates(self, mock_cq):
        config = BridgeTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_pillar(config, 10.0)

        mock_wp.box.assert_called_once_with(
            config.pillar_width,
            config.pillar_depth,
            config.pillar_height,
            centered=(True, True, False),
        )
        mock_wp.translate.assert_called_once_with((10.0, 0.0, config.base_height))

    @patch("filament_calibrator.bridge_model.cq")
    def test_custom_y_position(self, mock_cq):
        config = BridgeTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        _make_pillar(config, 5.0, y=3.0)

        mock_wp.translate.assert_called_once_with((5.0, 3.0, config.base_height))


# ---------------------------------------------------------------------------
# _make_bridge (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeBridge:
    @patch("filament_calibrator.bridge_model.cq")
    def test_creates_bridge_box_and_translates(self, mock_cq):
        config = BridgeTestConfig()

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp

        span = 30.0
        x_center = 15.0
        _make_bridge(config, x_center, span)

        bridge_width = span + 2 * config.pillar_width
        mock_wp.box.assert_called_once_with(
            bridge_width,
            config.pillar_depth,
            config.bridge_thickness,
            centered=(True, True, False),
        )
        z_bottom = config.base_height + config.pillar_height
        mock_wp.translate.assert_called_once_with((x_center, 0, z_bottom))


# ---------------------------------------------------------------------------
# _make_bridge_test (mocked CadQuery)
# ---------------------------------------------------------------------------


class TestMakeBridgeTest:
    @patch("filament_calibrator.bridge_model.cq")
    def test_union_calls_for_pillars_and_bridges(self, mock_cq):
        config = BridgeTestConfig(spans=(10.0, 20.0))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_bridge_test(config)

        # Each span produces 2 pillar unions + 1 bridge union = 3 unions per span
        assert mock_wp.union.call_count == 2 * 3

    @patch("filament_calibrator.bridge_model.cq")
    def test_single_span(self, mock_cq):
        config = BridgeTestConfig(spans=(25.0,))

        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        _make_bridge_test(config)

        # 1 span: 2 pillars + 1 bridge = 3 unions
        assert mock_wp.union.call_count == 3


# ---------------------------------------------------------------------------
# generate_bridge_stl
# ---------------------------------------------------------------------------


class TestGenerateBridgeStl:
    @patch("filament_calibrator.bridge_model.cq")
    def test_creates_output_dir(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = tmp_path / "nested" / "dir" / "bridge.stl"
        config = BridgeTestConfig()
        result = generate_bridge_stl(config, str(output))

        assert result == str(output)
        assert output.parent.exists()
        mock_cq.exporters.export.assert_called_once()

    @patch("filament_calibrator.bridge_model.cq")
    def test_returns_output_path(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = BridgeTestConfig()
        result = generate_bridge_stl(config, output)

        assert result == output

    @patch("filament_calibrator.bridge_model.cq")
    def test_exports_as_stl(self, mock_cq, tmp_path):
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        output = str(tmp_path / "test.stl")
        config = BridgeTestConfig()
        generate_bridge_stl(config, output)

        export_call = mock_cq.exporters.export.call_args
        assert export_call[1]["exportType"] == "STL"
        assert export_call[0][1] == output

    @patch("filament_calibrator.bridge_model.cq")
    def test_calls_ensure_cq(self, mock_cq, tmp_path):
        """_ensure_cq is called to ensure cadquery is loaded."""
        mock_wp = MagicMock()
        mock_cq.Workplane.return_value = mock_wp
        mock_wp.box.return_value = mock_wp
        mock_wp.translate.return_value = mock_wp
        mock_wp.union.return_value = mock_wp

        saved = mod.cq
        try:
            mod.cq = None
            mock_cq_impl = MagicMock()
            with patch.object(mod, "_ensure_cq_impl", return_value=mock_cq_impl):
                # Reset cq to our mock after _ensure_cq sets it
                with patch.object(mod, "cq", mock_cq):
                    generate_bridge_stl(BridgeTestConfig(), str(tmp_path / "t.stl"))
        finally:
            mod.cq = saved
