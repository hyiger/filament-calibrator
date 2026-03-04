"""Tests for filament_calibrator.flow_cli — volumetric flow CLI orchestration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

import gcode_lib as gl

from filament_calibrator.cli import _KNOWN_TYPES, _UNSET
from filament_calibrator.flow_cli import (
    MAX_LEVELS,
    _resolve_preset,
    _validate_flow_args,
    build_parser,
    main,
    run,
)


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_returns_parser(self):
        p = build_parser()
        assert isinstance(p, argparse.ArgumentParser)

    def test_required_args(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args([])  # missing required --start-speed etc.

    def test_defaults(self):
        p = build_parser()
        args = p.parse_args(["--start-speed", "5", "--end-speed", "20", "--step", "0.5"])
        assert args.start_speed == 5.0
        assert args.end_speed == 20.0
        assert args.step == 0.5
        assert args.level_height == 1.0
        assert args.filament_type == "PLA"
        assert args.layer_height == 0.2
        assert args.extrusion_width == 0.45
        assert args.bed_temp is _UNSET
        assert args.fan_speed is _UNSET
        assert args.nozzle_temp is _UNSET
        assert args.config_ini is None
        assert args.prusaslicer_path is None
        assert args.bed_center is None
        assert args.extra_slicer_args is None
        assert args.printer_url is None
        assert args.api_key is None
        assert args.no_upload is False
        assert args.print_after_upload is False
        assert args.output_dir is None
        assert args.keep_files is False
        assert args.verbose is False
        assert args.config is None

    def test_filament_type_help_lists_presets(self):
        p = build_parser()
        # Find the --filament-type action and check its raw help string.
        ft_action = [a for a in p._actions if "--filament-type" in getattr(a, "option_strings", [])][0]
        for name in _KNOWN_TYPES:
            assert name in ft_action.help

    def test_all_options(self):
        p = build_parser()
        args = p.parse_args([
            "--start-speed", "5",
            "--end-speed", "20",
            "--step", "0.5",
            "--level-height", "2.0",
            "--filament-type", "PETG",
            "--layer-height", "0.3",
            "--extrusion-width", "0.6",
            "--bed-temp", "80",
            "--fan-speed", "40",
            "--nozzle-temp", "250",
            "--config-ini", "/path/to/config.ini",
            "--prusaslicer-path", "/usr/bin/ps",
            "--bed-center", "90,90",
            "--printer-url", "http://10.0.0.1",
            "--api-key", "test-key",
            "--no-upload",
            "--print-after-upload",
            "--output-dir", "/tmp/out",
            "--keep-files",
            "--verbose",
            "--config", "/path/to/config.toml",
            "--extra-slicer-args", "--nozzle-diameter", "0.4",
        ])
        assert args.start_speed == 5.0
        assert args.end_speed == 20.0
        assert args.step == 0.5
        assert args.level_height == 2.0
        assert args.filament_type == "PETG"
        assert args.layer_height == 0.3
        assert args.extrusion_width == 0.6
        assert args.bed_temp == 80
        assert args.fan_speed == 40
        assert args.nozzle_temp == 250
        assert args.config_ini == "/path/to/config.ini"
        assert args.prusaslicer_path == "/usr/bin/ps"
        assert args.bed_center == "90,90"
        assert args.printer_url == "http://10.0.0.1"
        assert args.api_key == "test-key"
        assert args.no_upload is True
        assert args.print_after_upload is True
        assert args.output_dir == "/tmp/out"
        assert args.keep_files is True
        assert args.verbose is True
        assert args.config == "/path/to/config.toml"
        assert args.extra_slicer_args == ["--nozzle-diameter", "0.4"]


# ---------------------------------------------------------------------------
# _validate_flow_args
# ---------------------------------------------------------------------------


class TestValidateFlowArgs:
    def test_valid_range(self):
        assert _validate_flow_args(5.0, 20.0, 5.0) == 4

    def test_valid_small_step(self):
        assert _validate_flow_args(5.0, 20.0, 0.5) == 31

    def test_start_zero_exits(self):
        with pytest.raises(SystemExit, match="--start-speed must be positive"):
            _validate_flow_args(0.0, 10.0, 1.0)

    def test_start_negative_exits(self):
        with pytest.raises(SystemExit, match="--start-speed must be positive"):
            _validate_flow_args(-1.0, 10.0, 1.0)

    def test_step_zero_exits(self):
        with pytest.raises(SystemExit, match="--step must be positive"):
            _validate_flow_args(5.0, 20.0, 0.0)

    def test_step_negative_exits(self):
        with pytest.raises(SystemExit, match="--step must be positive"):
            _validate_flow_args(5.0, 20.0, -1.0)

    def test_end_less_than_start_exits(self):
        with pytest.raises(SystemExit, match="must be greater than"):
            _validate_flow_args(20.0, 5.0, 1.0)

    def test_end_equals_start_exits(self):
        with pytest.raises(SystemExit, match="must be greater than"):
            _validate_flow_args(10.0, 10.0, 1.0)

    def test_not_divisible_exits(self):
        with pytest.raises(SystemExit, match="not evenly divisible"):
            _validate_flow_args(5.0, 20.0, 4.0)

    def test_too_many_levels_exits(self):
        with pytest.raises(SystemExit, match="exceeds maximum"):
            _validate_flow_args(1.0, 100.0, 1.0)

    def test_max_levels_constant(self):
        assert MAX_LEVELS == 50


# ---------------------------------------------------------------------------
# _resolve_preset
# ---------------------------------------------------------------------------


class TestResolvePreset:
    def test_pla_preset(self):
        args = argparse.Namespace(
            filament_type="PLA",
            nozzle_temp=_UNSET, bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100
        # Nozzle temp uses hotend key
        assert r["nozzle_temp"] > 0

    def test_unknown_filament_fallback(self):
        args = argparse.Namespace(
            filament_type="EXOTIC",
            nozzle_temp=_UNSET, bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["nozzle_temp"] == 210
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100

    def test_explicit_overrides(self):
        args = argparse.Namespace(
            filament_type="PLA",
            nozzle_temp=280, bed_temp=90, fan_speed=50,
        )
        r = _resolve_preset(args)
        assert r["nozzle_temp"] == 280
        assert r["bed_temp"] == 90
        assert r["fan_speed"] == 50

    def test_petg_preset(self):
        args = argparse.Namespace(
            filament_type="PETG",
            nozzle_temp=_UNSET, bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        petg = gl.FILAMENT_PRESETS["PETG"]
        assert r["nozzle_temp"] == int(petg["hotend"])
        assert r["bed_temp"] == int(petg["bed"])
        assert r["fan_speed"] == int(petg["fan"])

    def test_case_insensitive(self):
        args = argparse.Namespace(
            filament_type="pla",
            nozzle_temp=_UNSET, bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        pla = gl.FILAMENT_PRESETS["PLA"]
        assert r["nozzle_temp"] == int(pla["hotend"])
        assert r["bed_temp"] == int(pla["bed"])

    def test_partial_override(self):
        """User overrides only nozzle; bed and fan come from preset."""
        args = argparse.Namespace(
            filament_type="PLA",
            nozzle_temp=250, bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        pla = gl.FILAMENT_PRESETS["PLA"]
        assert r["nozzle_temp"] == 250
        assert r["bed_temp"] == int(pla["bed"])
        assert r["fan_speed"] == int(pla["fan"])


# ---------------------------------------------------------------------------
# run — full pipeline
# ---------------------------------------------------------------------------


class TestRun:
    def _make_args(self, tmp_path, **overrides):
        defaults = dict(
            start_speed=5.0, end_speed=10.0, step=5.0,
            level_height=1.0, filament_type="PLA",
            layer_height=0.2, extrusion_width=0.45,
            bed_temp=_UNSET, fan_speed=_UNSET, nozzle_temp=_UNSET,
            config_ini=None, prusaslicer_path=None,
            extra_slicer_args=None, bed_center=None,
            printer_url=None, api_key=None,
            no_upload=True, print_after_upload=False,
            output_dir=str(tmp_path), keep_files=False,
            config=None, verbose=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_full_pipeline_no_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        mock_gen.assert_called_once()
        mock_slice.assert_called_once()
        mock_levels.assert_called_once()
        mock_load.assert_called_once()
        mock_insert.assert_called_once()
        mock_save.assert_called_once()

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_slicer_failure_exits(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(
            ok=False, returncode=1, stderr="bad"
        )

        args = self._make_args(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code == 1

    @patch("filament_calibrator.flow_cli.gl.prusalink_upload")
    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_upload, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_upload.return_value = "specimen.gcode"

        args = self._make_args(
            tmp_path,
            no_upload=False,
            printer_url="http://192.168.1.100",
            api_key="key123",
            print_after_upload=True,
        )
        run(args)

        mock_upload.assert_called_once()
        call_kwargs = mock_upload.call_args[1]
        assert call_kwargs["base_url"] == "http://192.168.1.100"
        assert call_kwargs["api_key"] == "key123"
        assert call_kwargs["print_after_upload"] is True

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_upload_missing_url_exits(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        args = self._make_args(
            tmp_path,
            no_upload=False,
            printer_url=None,
            api_key=None,
        )
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code == 1

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_keep_files(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        stl = tmp_path / "flow_specimen_PLA_5.0_5.0x2.stl"
        raw_gcode = tmp_path / "flow_specimen_PLA_5.0_5.0x2_raw.gcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, keep_files=True)
        run(args)

        assert stl.exists()
        assert raw_gcode.exists()

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_no_keep_files_cleans_up(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        stl = tmp_path / "flow_specimen_PLA_5.0_5.0x2.stl"
        raw_gcode = tmp_path / "flow_specimen_PLA_5.0_5.0x2_raw.gcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, keep_files=False)
        run(args)

        assert not stl.exists()
        assert not raw_gcode.exists()

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_verbose_output(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer", "--slice"], stdout="", stderr=""
        )
        mock_levels.return_value = [
            MagicMock(z_start=0.0, z_end=1.0, flow_rate=5.0, feedrate=6666.67),
        ]
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True)
        run(args)

        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out
        assert "No config file loaded" in captured.out
        assert "Filament preset 'PLA' found" in captured.out
        assert "Bed center:" in captured.out
        assert "PrusaSlicer command:" in captured.out
        assert "Flow levels:" in captured.out

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_no_verbose_no_debug(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=False)
        run(args)

        captured = capsys.readouterr()
        assert "[DEBUG]" not in captured.out

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_verbose_shows_slicer_stdout(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"],
            stdout="Slicing complete in 2.1s", stderr=""
        )
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True)
        run(args)

        captured = capsys.readouterr()
        assert "PrusaSlicer stdout: Slicing complete in 2.1s" in captured.out

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_verbose_unknown_filament(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True, filament_type="EXOTIC")
        run(args)

        captured = capsys.readouterr()
        assert "not in presets" in captured.out
        assert "fallback defaults" in captured.out

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_verbose_shows_config_file(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path, capsys
    ):
        cfg = tmp_path / "test.toml"
        cfg.write_text('filament-type = "PLA"\n')

        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True, config=str(cfg))
        run(args)

        captured = capsys.readouterr()
        assert "Config file:" in captured.out
        assert str(cfg) in captured.out

    @patch("filament_calibrator.flow_cli.gl.prusalink_upload")
    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_verbose_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_upload, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_upload.return_value = "specimen.gcode"

        args = self._make_args(
            tmp_path, verbose=True,
            no_upload=False,
            printer_url="http://192.168.1.100",
            api_key="key123",
            print_after_upload=True,
        )
        run(args)

        captured = capsys.readouterr()
        assert "Upload target: http://192.168.1.100" in captured.out
        assert "Print after upload: True" in captured.out

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_slicer_receives_correct_args(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(
            tmp_path,
            layer_height=0.3,
            extrusion_width=0.6,
            bed_center="90,90",
        )
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["layer_height"] == 0.3
        assert slice_kwargs["extrusion_width"] == 0.6
        assert slice_kwargs["bed_center"] == "90,90"

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_preset_temps_passed_to_slicer(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        """Filament preset nozzle/bed/fan are forwarded to slice_flow_specimen."""
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        pla = gl.FILAMENT_PRESETS["PLA"]
        args = self._make_args(tmp_path, filament_type="PLA")
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["nozzle_temp"] == int(pla["hotend"])
        assert slice_kwargs["bed_temp"] == int(pla["bed"])
        assert slice_kwargs["fan_speed"] == int(pla["fan"])

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_explicit_temps_override_preset_to_slicer(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        """Explicit --nozzle-temp/--bed-temp/--fan-speed override preset in slicer call."""
        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(
            tmp_path,
            filament_type="PLA",
            nozzle_temp=280,
            bed_temp=90,
            fan_speed=50,
        )
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["nozzle_temp"] == 280
        assert slice_kwargs["bed_temp"] == 90
        assert slice_kwargs["fan_speed"] == 50

    @patch("filament_calibrator.flow_cli.gl.save")
    @patch("filament_calibrator.flow_cli.gl.load")
    @patch("filament_calibrator.flow_cli.insert_flow_rates")
    @patch("filament_calibrator.flow_cli.compute_flow_levels")
    @patch("filament_calibrator.flow_cli.slice_flow_specimen")
    @patch("filament_calibrator.flow_cli.generate_flow_specimen_stl")
    def test_config_file_applies_defaults(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, tmp_path
    ):
        cfg = tmp_path / "test.toml"
        cfg.write_text('filament-type = "PETG"\n')

        mock_gen.return_value = str(tmp_path / "specimen.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, config=str(cfg))
        run(args)

        gen_call = mock_gen.call_args
        specimen_config = gen_call[0][0]
        assert specimen_config.filament_type == "PETG"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("filament_calibrator.flow_cli.run")
    def test_parses_and_runs(self, mock_run):
        main(["--start-speed", "5", "--end-speed", "20",
              "--step", "0.5", "--no-upload"])
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.start_speed == 5.0
        assert args.end_speed == 20.0
        assert args.step == 0.5
        assert args.no_upload is True

    @patch("filament_calibrator.flow_cli.run")
    def test_verbose_flag(self, mock_run):
        main(["--start-speed", "5", "--end-speed", "10",
              "--step", "5", "-v"])
        args = mock_run.call_args[0][0]
        assert args.verbose is True
