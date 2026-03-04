"""Tests for filament_calibrator.cli — CLI orchestration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

import gcode_lib as gl

from filament_calibrator.cli import (
    _UNSET,
    _KNOWN_TYPES,
    _compute_num_tiers,
    build_parser,
    main,
    resolve_preset,
    run,
    _resolve_output_dir,
    _build_tower_config,
)
from filament_calibrator.model import TowerConfig


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_returns_parser(self):
        p = build_parser()
        assert isinstance(p, argparse.ArgumentParser)

    def test_defaults(self):
        p = build_parser()
        args = p.parse_args([])
        assert args.high_temp is _UNSET
        assert args.low_temp is _UNSET
        assert args.temp_jump == 5
        assert args.filament_type == "PLA"
        assert args.brand_top == ""
        assert args.brand_bottom == ""
        assert args.bed_temp is _UNSET
        assert args.fan_speed is _UNSET
        assert args.config_ini is None
        assert args.prusaslicer_path is None
        assert args.extra_slicer_args is None
        assert args.printer_url is None
        assert args.api_key is None
        assert args.no_upload is False
        assert args.print_after_upload is False
        assert args.output_dir is None
        assert args.keep_files is False

    def test_all_options(self):
        p = build_parser()
        # --extra-slicer-args must come last because nargs=REMAINDER consumes
        # everything after it
        args = p.parse_args([
            "--high-temp", "250",
            "--low-temp", "220",
            "--temp-jump", "5",
            "--filament-type", "PETG",
            "--brand-top", "BrandA",
            "--brand-bottom", "BrandB",
            "--bed-temp", "85",
            "--fan-speed", "30",
            "--config-ini", "/path/to/config.ini",
            "--prusaslicer-path", "/usr/bin/ps",
            "--printer-url", "http://10.0.0.1",
            "--api-key", "test-key",
            "--no-upload",
            "--print-after-upload",
            "--output-dir", "/tmp/out",
            "--keep-files",
            "--extra-slicer-args", "--nozzle-diameter", "0.4",
        ])
        assert args.high_temp == 250
        assert args.low_temp == 220
        assert args.temp_jump == 5
        assert args.filament_type == "PETG"
        assert args.brand_top == "BrandA"
        assert args.brand_bottom == "BrandB"
        assert args.bed_temp == 85
        assert args.fan_speed == 30
        assert args.config_ini == "/path/to/config.ini"
        assert args.prusaslicer_path == "/usr/bin/ps"
        assert args.extra_slicer_args == ["--nozzle-diameter", "0.4"]
        assert args.printer_url == "http://10.0.0.1"
        assert args.api_key == "test-key"
        assert args.no_upload is True
        assert args.print_after_upload is True
        assert args.output_dir == "/tmp/out"
        assert args.keep_files is True

    def test_known_types(self):
        """_KNOWN_TYPES lists sorted preset names from gcode-lib."""
        assert "ABS" in _KNOWN_TYPES
        assert "PLA" in _KNOWN_TYPES
        assert "PETG" in _KNOWN_TYPES
        assert _KNOWN_TYPES == sorted(_KNOWN_TYPES)


# ---------------------------------------------------------------------------
# _resolve_output_dir
# ---------------------------------------------------------------------------


class TestResolveOutputDir:
    def test_with_explicit_dir(self, tmp_path):
        d = tmp_path / "my_output"
        result = _resolve_output_dir(str(d))
        assert result == d
        assert d.exists()

    def test_creates_nested_dir(self, tmp_path):
        d = tmp_path / "a" / "b" / "c"
        result = _resolve_output_dir(str(d))
        assert d.exists()

    def test_none_creates_temp(self):
        result = _resolve_output_dir(None)
        assert result.exists()
        assert "temperature-tower" in str(result)


# ---------------------------------------------------------------------------
# resolve_preset
# ---------------------------------------------------------------------------


class TestResolvePreset:
    def test_pla_defaults(self):
        """PLA preset: temp_max=230, temp_min=190, bed=60, fan=100."""
        args = argparse.Namespace(
            filament_type="PLA", high_temp=_UNSET, low_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 230
        assert r["low_temp"] == 190
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100

    def test_petg_defaults(self):
        """PETG preset: temp_max=260, temp_min=220, bed=80, fan=40."""
        args = argparse.Namespace(
            filament_type="PETG", high_temp=_UNSET, low_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 260
        assert r["low_temp"] == 220
        assert r["bed_temp"] == 80
        assert r["fan_speed"] == 40

    def test_abs_defaults(self):
        """ABS preset: temp_max=270, temp_min=230, bed=100, fan=20."""
        args = argparse.Namespace(
            filament_type="ABS", high_temp=_UNSET, low_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 270
        assert r["low_temp"] == 230
        assert r["bed_temp"] == 100
        assert r["fan_speed"] == 20

    def test_case_insensitive(self):
        """Filament type lookup is case-insensitive."""
        args = argparse.Namespace(
            filament_type="pla", high_temp=_UNSET, low_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 230
        assert r["low_temp"] == 190
        assert r["bed_temp"] == 60

    def test_unknown_filament_uses_fallback(self):
        """Unknown filament type uses conservative defaults."""
        args = argparse.Namespace(
            filament_type="EXOTIC", high_temp=_UNSET, low_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 230
        assert r["low_temp"] == 190
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100

    def test_explicit_high_temp_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PLA", high_temp=240, low_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 240
        assert r["low_temp"] == 190  # still from preset
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100

    def test_explicit_low_temp_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PLA", high_temp=_UNSET, low_temp=200,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 230  # still from preset
        assert r["low_temp"] == 200

    def test_explicit_bed_temp_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PETG", high_temp=_UNSET, low_temp=_UNSET,
            bed_temp=90, fan_speed=_UNSET,
        )
        r = resolve_preset(args)
        assert r["bed_temp"] == 90
        assert r["fan_speed"] == 40  # still from preset

    def test_explicit_fan_speed_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PLA", high_temp=_UNSET, low_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=50,
        )
        r = resolve_preset(args)
        assert r["fan_speed"] == 50
        assert r["bed_temp"] == 60  # still from preset

    def test_all_explicit_overrides(self):
        """When all values are explicit, preset is ignored."""
        args = argparse.Namespace(
            filament_type="PLA", high_temp=250, low_temp=200,
            bed_temp=70, fan_speed=80,
        )
        r = resolve_preset(args)
        assert r["high_temp"] == 250
        assert r["low_temp"] == 200
        assert r["bed_temp"] == 70
        assert r["fan_speed"] == 80


# ---------------------------------------------------------------------------
# _build_tower_config
# ---------------------------------------------------------------------------


class TestComputeNumTiers:
    def test_normal_range(self):
        # 230→190 step 5 → 9 tiers
        assert _compute_num_tiers(230, 190, 5) == 9

    def test_small_range(self):
        # 210→200 step 10 → 2 tiers
        assert _compute_num_tiers(210, 200, 10) == 2

    def test_max_ten_tiers(self):
        # 250→200 step 5 → 11 tiers → error
        with pytest.raises(SystemExit):
            _compute_num_tiers(250, 200, 5)

    def test_high_equals_low_exits(self):
        with pytest.raises(SystemExit):
            _compute_num_tiers(200, 200, 5)

    def test_high_less_than_low_exits(self):
        with pytest.raises(SystemExit):
            _compute_num_tiers(190, 200, 5)

    def test_not_divisible_exits(self):
        # 230→190 = 40, not divisible by 7
        with pytest.raises(SystemExit):
            _compute_num_tiers(230, 190, 7)

    def test_ten_tiers_allowed(self):
        # 250→200 step 5 → 11 (too many), but 245→200 step 5 → 10 (ok)
        assert _compute_num_tiers(245, 200, 5) == 10


class TestBuildTowerConfig:
    def test_maps_args(self):
        args = argparse.Namespace(
            temp_jump=5,
            filament_type="PETG", brand_top="X", brand_bottom="Y",
        )
        config = _build_tower_config(args, high_temp=250, low_temp=220)
        assert isinstance(config, TowerConfig)
        assert config.high_temp == 250
        assert config.temp_jump == 5
        assert config.num_tiers == 7  # (250-220)/5 + 1 = 7
        assert config.filament_type == "PETG"
        assert config.brand_top == "X"
        assert config.brand_bottom == "Y"


# ---------------------------------------------------------------------------
# run — full pipeline
# ---------------------------------------------------------------------------


class TestRun:
    def _make_args(self, tmp_path, **overrides):
        defaults = dict(
            high_temp=_UNSET, low_temp=_UNSET, temp_jump=5,
            filament_type="PLA", brand_top="", brand_bottom="",
            bed_temp=_UNSET, fan_speed=_UNSET,
            config_ini=None, prusaslicer_path=None,
            extra_slicer_args=None,
            printer_url=None, api_key=None,
            no_upload=True, print_after_upload=False,
            output_dir=str(tmp_path), keep_files=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_full_pipeline_no_upload(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        mock_gen.assert_called_once()
        mock_slice.assert_called_once()
        # Verify nozzle_temp, bed_temp and fan_speed are passed to slicer
        slice_kwargs = mock_slice.call_args[1]
        # PLA preset: high_temp = temp_max = 230
        assert slice_kwargs["nozzle_temp"] == 230
        assert slice_kwargs["bed_temp"] == 60   # PLA preset
        assert slice_kwargs["fan_speed"] == 100  # PLA preset
        mock_tiers.assert_called_once()
        mock_load.assert_called_once()
        mock_insert.assert_called_once()
        mock_save.assert_called_once()

    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_slicer_failure_exits(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=False, returncode=1, stderr="bad"
        )

        args = self._make_args(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code == 1

    @patch("filament_calibrator.cli.gl.prusalink_upload")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_upload(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, mock_upload, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_upload.return_value = "tower.gcode"

        args = self._make_args(
            tmp_path,
            no_upload=False,
            printer_url="http://192.168.1.100",
            api_key="key123",
            print_after_upload=True,
        )
        run(args)

        mock_upload.assert_called_once()
        call_kwargs = mock_upload.call_args
        assert call_kwargs[1]["base_url"] == "http://192.168.1.100"
        assert call_kwargs[1]["api_key"] == "key123"
        assert call_kwargs[1]["print_after_upload"] is True

    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_upload_missing_url_exits(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(
            tmp_path,
            no_upload=False,
            printer_url=None,
            api_key=None,
        )
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code == 1

    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_keep_files(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        # PLA preset: high=230, low=190, jump=5 → 9 tiers
        stl = tmp_path / "temp_tower_PLA_230_5x9.stl"
        raw_gcode = tmp_path / "temp_tower_PLA_230_5x9_raw.gcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, keep_files=True)
        run(args)

        assert stl.exists()
        assert raw_gcode.exists()

    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_no_keep_files_cleans_up(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        stl = tmp_path / "temp_tower_PLA_230_5x9.stl"
        raw_gcode = tmp_path / "temp_tower_PLA_230_5x9_raw.gcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, keep_files=False)
        run(args)

        assert not stl.exists()
        assert not raw_gcode.exists()

    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_explicit_overrides_passed_to_slicer(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, bed_temp=85, fan_speed=50)
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["bed_temp"] == 85
        assert slice_kwargs["fan_speed"] == 50


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("filament_calibrator.cli.run")
    def test_parses_and_runs(self, mock_run):
        main(["--no-upload", "--high-temp", "200"])
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.high_temp == 200
        assert args.no_upload is True

    @patch("filament_calibrator.cli.run")
    def test_defaults(self, mock_run):
        main([])
        args = mock_run.call_args[0][0]
        assert args.high_temp is _UNSET
        assert args.low_temp is _UNSET

    @patch("filament_calibrator.cli.run")
    def test_bed_temp_and_fan_speed(self, mock_run):
        main(["--bed-temp", "90", "--fan-speed", "60"])
        args = mock_run.call_args[0][0]
        assert args.bed_temp == 90
        assert args.fan_speed == 60


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------


class TestMainModule:
    @patch("filament_calibrator.cli.main")
    def test_dunder_main(self, mock_main):
        """__main__.py calls main() when executed."""
        import importlib
        import filament_calibrator.__main__  # noqa: F401
        # Importing __main__ triggers main() call; verify it was called
        mock_main.assert_called()
