"""Tests for filament_calibrator.retraction_cli — retraction CLI orchestration."""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import gcode_lib as gl

from filament_calibrator.cli import _KNOWN_TYPES, _UNSET
from filament_calibrator.retraction_cli import (
    MAX_LEVELS,
    _find_config_path,
    _validate_retraction_args,
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

    def test_defaults(self):
        p = build_parser()
        args = p.parse_args([])
        assert args.start_retraction == 0.0
        assert args.end_retraction == 2.0
        assert args.retraction_step == 0.1
        assert args.level_height == 1.0
        assert args.filament_type == "PLA"
        assert args.nozzle_size == 0.4
        assert args.layer_height is _UNSET
        assert args.extrusion_width is _UNSET
        assert args.bed_temp is _UNSET
        assert args.fan_speed is _UNSET
        assert args.nozzle_temp is _UNSET
        assert args.config_ini is None
        assert args.prusaslicer_path is None
        assert args.bed_center is None
        assert args.extra_slicer_args is None
        assert args.printer == "COREONE"
        assert args.printer_url is None
        assert args.api_key is None
        assert args.no_upload is False
        assert args.print_after_upload is False
        assert args.config is None
        assert args.output_dir is None
        assert args.keep_files is False
        assert args.ascii_gcode is False
        assert args.verbose is False

    def test_all_options(self):
        p = build_parser()
        args = p.parse_args([
            "--start-retraction", "0.5",
            "--end-retraction", "3.0",
            "--retraction-step", "0.5",
            "--level-height", "2.0",
            "--filament-type", "PETG",
            "--nozzle-size", "0.6",
            "--layer-height", "0.3",
            "--extrusion-width", "0.68",
            "--bed-temp", "80",
            "--fan-speed", "50",
            "--nozzle-temp", "240",
            "--config-ini", "/path/to/config.ini",
            "--prusaslicer-path", "/usr/bin/prusa-slicer",
            "--bed-center", "90,90",
            "--printer-url", "http://192.168.1.100",
            "--api-key", "key123",
            "--no-upload",
            "--print-after-upload",
            "--config", "/path/to/config.toml",
            "--output-dir", "/tmp/retraction",
            "--keep-files",
            "-v",
        ])
        assert args.start_retraction == 0.5
        assert args.end_retraction == 3.0
        assert args.retraction_step == 0.5
        assert args.level_height == 2.0
        assert args.filament_type == "PETG"
        assert args.nozzle_size == 0.6
        assert args.layer_height == 0.3
        assert args.extrusion_width == 0.68
        assert args.bed_temp == 80
        assert args.fan_speed == 50
        assert args.nozzle_temp == 240
        assert args.verbose is True

    def test_filament_type_help_lists_presets(self):
        p = build_parser()
        help_text = p.format_help()
        assert "PLA" in help_text


# ---------------------------------------------------------------------------
# _validate_retraction_args
# ---------------------------------------------------------------------------


class TestValidateRetractionArgs:
    def test_valid_range(self):
        assert _validate_retraction_args(0.0, 2.0, 0.1) == 21

    def test_start_zero_is_valid(self):
        num = _validate_retraction_args(0.0, 0.5, 0.5)
        assert num == 2

    def test_start_negative_exits(self):
        with pytest.raises(SystemExit, match="non-negative"):
            _validate_retraction_args(-0.1, 2.0, 0.1)

    def test_step_zero_exits(self):
        with pytest.raises(SystemExit, match="positive"):
            _validate_retraction_args(0.0, 2.0, 0.0)

    def test_step_negative_exits(self):
        with pytest.raises(SystemExit, match="positive"):
            _validate_retraction_args(0.0, 2.0, -0.1)

    def test_level_height_zero_exits(self):
        with pytest.raises(SystemExit, match="--level-height must be positive"):
            _validate_retraction_args(0.0, 2.0, 0.1, 0.0)

    def test_level_height_negative_exits(self):
        with pytest.raises(SystemExit, match="--level-height must be positive"):
            _validate_retraction_args(0.0, 2.0, 0.1, -1.0)

    def test_end_equal_exits(self):
        with pytest.raises(SystemExit, match="greater than"):
            _validate_retraction_args(1.0, 1.0, 0.1)

    def test_end_less_exits(self):
        with pytest.raises(SystemExit, match="greater than"):
            _validate_retraction_args(1.0, 0.5, 0.1)

    def test_not_divisible_exits(self):
        with pytest.raises(SystemExit, match="evenly divisible"):
            _validate_retraction_args(0.0, 1.0, 0.3)

    def test_too_many_levels_exits(self):
        with pytest.raises(SystemExit, match="exceeds maximum"):
            _validate_retraction_args(0.0, 5.1, 0.1)

    def test_max_levels_constant(self):
        assert MAX_LEVELS == 50


# ---------------------------------------------------------------------------
# _find_config_path
# ---------------------------------------------------------------------------


class TestFindConfigPath:
    def test_returns_explicit_path(self):
        assert _find_config_path("/some/path.toml") == "/some/path.toml"

    def test_returns_none_when_no_defaults_exist(self):
        """When explicit is None and no default config files exist."""
        with patch(
            "filament_calibrator.retraction_cli._FIND_CONFIG_PATHS",
            (Path("/nonexistent/path/a.toml"), Path("/nonexistent/path/b.toml")),
        ):
            assert _find_config_path(None) is None


# ---------------------------------------------------------------------------
# run — full pipeline
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.fixture(autouse=True)
    def _fix_suffix(self):
        with patch("gcode_lib.unique_suffix", return_value="abc12"):
            yield

    def _make_args(self, tmp_path, **overrides):
        defaults = dict(
            start_retraction=0.0, end_retraction=0.5,
            retraction_step=0.5,
            level_height=1.0, filament_type="PLA",
            nozzle_size=0.4,
            layer_height=_UNSET, extrusion_width=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET, nozzle_temp=_UNSET,
            config_ini=None, prusaslicer_path=None,
            extra_slicer_args=None, bed_center=None,
            printer="COREONE",
            printer_url=None, api_key=None,
            no_upload=True, print_after_upload=False,
            output_dir=str(tmp_path), keep_files=False,
            ascii_gcode=False,
            config=None, verbose=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_full_pipeline_no_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_slicer_failure_exits(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=False, returncode=1, stderr="bad"
        )

        args = self._make_args(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code == 1

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.prusalink_upload")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_upload,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
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
        call_kwargs = mock_upload.call_args[1]
        assert call_kwargs["base_url"] == "http://192.168.1.100"
        assert call_kwargs["api_key"] == "key123"
        assert call_kwargs["print_after_upload"] is True

    @patch("filament_calibrator.retraction_cli.load_config", return_value={})
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_upload_missing_url_exits(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        mock_load_config, tmp_path
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_keep_files(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        stl = tmp_path / "retraction_tower_PLA_0.0_0.5x2_abc12.stl"
        raw_gcode = tmp_path / "retraction_tower_PLA_0.0_0.5x2_abc12_raw.bgcode"
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_no_keep_files_cleans_up(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        stl = tmp_path / "retraction_tower_PLA_0.0_0.5x2_abc12.stl"
        raw_gcode = tmp_path / "retraction_tower_PLA_0.0_0.5x2_abc12_raw.bgcode"
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

    @patch("filament_calibrator.retraction_cli.load_config", return_value={})
    @patch("filament_calibrator.retraction_cli._find_config_path",
           return_value=None)
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_verbose_output(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        mock_find_config, mock_load_config, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer", "--slice"], stdout="", stderr=""
        )
        mock_levels.return_value = [
            MagicMock(
                z_start=1.0, z_end=2.0, retraction_length=0.0,
            ),
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
        assert "Retraction levels:" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_no_verbose_no_debug(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=False)
        run(args)

        captured = capsys.readouterr()
        assert "[DEBUG]" not in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_verbose_shows_slicer_stdout(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_verbose_unknown_filament(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(
            tmp_path, verbose=True, filament_type="EXOTIC",
        )
        run(args)

        captured = capsys.readouterr()
        assert "not in presets" in captured.out
        assert "fallback defaults" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_verbose_shows_config_file(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path, capsys
    ):
        cfg = tmp_path / "test.toml"
        cfg.write_text('filament-type = "PLA"\n')

        mock_gen.return_value = str(tmp_path / "tower.stl")
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.prusalink_upload")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_verbose_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_upload,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_upload.return_value = "tower.gcode"

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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_slicer_receives_correct_args(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_preset_temps_passed_to_slicer(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        """Filament preset nozzle/bed/fan are forwarded to slicer."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_explicit_temps_override_preset(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        """Explicit --nozzle-temp/--bed-temp/--fan-speed override preset."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_nozzle_size_derivation(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        """Nozzle size derives layer_height and extrusion_width."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, nozzle_size=0.6)
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["layer_height"] == pytest.approx(0.3)
        assert slice_kwargs["extrusion_width"] == pytest.approx(
            round(0.6 * 1.125, 2),
        )

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_ascii_gcode(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        """--ascii-gcode passes binary_gcode=False to slicer."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, ascii_gcode=True)
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["binary_gcode"] is False

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_config_file_applies_defaults(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        cfg = tmp_path / "test.toml"
        cfg.write_text('filament-type = "PETG"\n')

        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, config=str(cfg))
        run(args)

        gen_call = mock_gen.call_args
        tower_config = gen_call[0][0]
        assert tower_config.filament_type == "PETG"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_no_printer_skips_metadata(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        """When --printer is None, patch_slicer_metadata is not called."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, printer=None)
        run(args)

        mock_patch_meta.assert_not_called()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_invalid_printer_exits(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        """Unknown printer name causes sys.exit via resolve_printer ValueError."""
        with patch(
            "filament_calibrator.retraction_cli.gl.resolve_printer",
            side_effect=ValueError("Unknown printer 'BADPRINTER'"),
        ):
            args = self._make_args(tmp_path, printer="BADPRINTER")
            with pytest.raises(SystemExit, match="Unknown printer"):
                run(args)

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_enclosure_filament_disables_cool_fan(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path
    ):
        """ABS (enclosure filament) sets use_cool_fan=False in start G-code."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, filament_type="ABS")
        with patch(
            "filament_calibrator.retraction_cli.gl.render_start_gcode",
            return_value="start",
        ) as mock_start, patch(
            "filament_calibrator.retraction_cli.gl.render_end_gcode",
            return_value="end",
        ):
            run(args)
            mock_start.assert_called_once()
            assert mock_start.call_args[1]["cool_fan"] is False

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.retraction_cli.gl.save")
    @patch("filament_calibrator.retraction_cli.gl.load")
    @patch("filament_calibrator.retraction_cli.insert_retraction_commands")
    @patch("filament_calibrator.retraction_cli.compute_retraction_levels")
    @patch("filament_calibrator.retraction_cli.slice_retraction_specimen")
    @patch("filament_calibrator.retraction_cli.generate_retraction_tower_stl")
    def test_prints_retraction_table(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta,
        tmp_path, capsys
    ):
        """Pipeline prints a retraction length lookup table."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = [
            MagicMock(z_start=1.0, z_end=2.0, retraction_length=0.0),
            MagicMock(z_start=2.0, z_end=3.0, retraction_length=0.5),
        ]
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        captured = capsys.readouterr()
        assert "Retraction length by height:" in captured.out
        assert "0.00 mm" in captured.out
        assert "0.50 mm" in captured.out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("filament_calibrator.retraction_cli.run")
    def test_main_parses_and_runs(self, mock_run):
        main(["--no-upload"])
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.no_upload is True
        assert args.start_retraction == 0.0
        assert args.end_retraction == 2.0
