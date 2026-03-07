"""Tests for filament_calibrator.em_cli — extrusion multiplier CLI orchestration."""
from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

import gcode_lib as gl

from filament_calibrator.cli import _KNOWN_TYPES, _UNSET
from filament_calibrator.em_cli import (
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

    def test_no_required_args(self):
        """Unlike flow/PA CLIs, EM has no required arguments."""
        p = build_parser()
        args = p.parse_args([])
        assert args.filament_type == "PLA"

    def test_defaults(self):
        p = build_parser()
        args = p.parse_args([])
        assert args.filament_type == "PLA"
        assert args.cube_size == 40.0
        assert args.nozzle_size == 0.4
        assert args.nozzle_high_flow is False
        assert args.nozzle_hardened is False
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
        assert args.output_dir is None
        assert args.keep_files is False
        assert args.ascii_gcode is False
        assert args.verbose is False
        assert args.config is None

    def test_all_options(self):
        p = build_parser()
        args = p.parse_args([
            "--filament-type", "PETG",
            "--cube-size", "30",
            "--nozzle-size", "0.6",
            "--layer-height", "0.3",
            "--extrusion-width", "0.68",
            "--bed-temp", "85",
            "--fan-speed", "50",
            "--nozzle-temp", "240",
            "--config-ini", "/tmp/config.ini",
            "--prusaslicer-path", "/usr/bin/prusa-slicer",
            "--bed-center", "100,100",
            "--printer", "MK4S",
            "--printer-url", "http://192.168.1.50",
            "--api-key", "secret",
            "--no-upload",
            "--print-after-upload",
            "--config", "/tmp/config.toml",
            "--output-dir", "/tmp/out",
            "--keep-files",
            "--ascii-gcode",
            "-v",
        ])
        assert args.filament_type == "PETG"
        assert args.cube_size == 30.0
        assert args.nozzle_size == 0.6
        assert args.layer_height == 0.3
        assert args.extrusion_width == 0.68
        assert args.bed_temp == 85
        assert args.fan_speed == 50
        assert args.nozzle_temp == 240
        assert args.config_ini == "/tmp/config.ini"
        assert args.prusaslicer_path == "/usr/bin/prusa-slicer"
        assert args.bed_center == "100,100"
        assert args.printer == "MK4S"
        assert args.printer_url == "http://192.168.1.50"
        assert args.api_key == "secret"
        assert args.no_upload is True
        assert args.print_after_upload is True
        assert args.config == "/tmp/config.toml"
        assert args.output_dir == "/tmp/out"
        assert args.keep_files is True
        assert args.ascii_gcode is True
        assert args.verbose is True


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.fixture(autouse=True)
    def _fix_suffix(self):
        with patch("gcode_lib.unique_suffix", return_value="abc12"):
            yield

    def _make_args(self, tmp_path, **overrides):
        defaults = dict(
            filament_type="PLA",
            cube_size=40.0,
            nozzle_size=0.4,
            nozzle_high_flow=False, nozzle_hardened=False,
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
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_full_pipeline_no_upload(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path)
        run(args)

        mock_gen.assert_called_once()
        mock_slice.assert_called_once()
        mock_load.assert_called_once()
        mock_save.assert_called_once()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_slicer_failure_exits(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(
            ok=False, returncode=1, stderr="bad"
        )

        args = self._make_args(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code == 1

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.prusalink_upload")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_upload(
        self, mock_gen, mock_slice, mock_load, mock_save, mock_upload,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])
        mock_upload.return_value = "cube.gcode"

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

    @patch("filament_calibrator.em_cli.load_config", return_value={})
    def test_upload_missing_url_exits(self, mock_cfg, tmp_path):
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
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_keep_files(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        """Intermediate files preserved when --keep-files is set."""
        stl = tmp_path / "em_cube_PLA_abc12.stl"
        raw = tmp_path / "em_cube_PLA_abc12_raw.bgcode"
        stl.touch()
        raw.touch()
        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, keep_files=True)
        run(args)

        assert stl.exists()
        assert raw.exists()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_no_keep_files_cleans_up(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        """Intermediate files removed by default."""
        stl = tmp_path / "em_cube_PLA_abc12.stl"
        raw = tmp_path / "em_cube_PLA_abc12_raw.bgcode"
        stl.touch()
        raw.touch()
        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, keep_files=False)
        run(args)

        assert not stl.exists()
        assert not raw.exists()

    @patch("filament_calibrator.em_cli._find_config_path", return_value=None)
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_verbose_output(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, mock_find_cfg, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True, cmd=["ps"], stdout="", stderr="")
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, verbose=True)
        run(args)

        out = capsys.readouterr().out
        assert "[DEBUG]" in out
        assert "No config file loaded" in out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_slicer_receives_correct_args(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, nozzle_size=0.6)
        run(args)

        call_kwargs = mock_slice.call_args[1]
        assert call_kwargs["layer_height"] == 0.3  # 0.6 * 0.5
        assert call_kwargs["extrusion_width"] == round(0.6 * 1.125, 2)
        assert call_kwargs["nozzle_diameter"] == 0.6

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_prints_expected_wall_thickness(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path)
        run(args)

        out = capsys.readouterr().out
        assert "Expected wall thickness: 0.45 mm" in out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_ascii_gcode(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, ascii_gcode=True)
        run(args)

        call_kwargs = mock_slice.call_args[1]
        assert call_kwargs["binary_gcode"] is False

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_config_ini_forwarded(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, config_ini="/tmp/my.ini")
        run(args)

        call_kwargs = mock_slice.call_args[1]
        assert call_kwargs["config_ini"] == "/tmp/my.ini"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_custom_cube_size(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, cube_size=30.0)
        run(args)

        config_arg = mock_gen.call_args[0][0]
        assert config_arg.size == 30.0

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_verbose_unknown_filament(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        """Unknown filament type triggers fallback debug message."""
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True, cmd=["ps"], stdout="", stderr="")
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, filament_type="MYSTERY", verbose=True)
        run(args)

        out = capsys.readouterr().out
        assert "not in presets" in out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_verbose_config_loaded(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        """Config file path is logged when verbose."""
        config_file = tmp_path / "filament-calibrator.toml"
        config_file.write_text("")
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True, cmd=["ps"], stdout="out", stderr="")
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(
            tmp_path, verbose=True,
            config=str(config_file),
        )
        run(args)

        out = capsys.readouterr().out
        assert "[DEBUG] Config file:" in out
        assert "[DEBUG] PrusaSlicer stdout:" in out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_printer_none(
        self, mock_gen, mock_slice, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        """Pipeline works when printer is None (no metadata patching)."""
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_load.return_value = MagicMock(lines=[])

        args = self._make_args(tmp_path, printer=None)
        run(args)

        mock_resolve.assert_not_called()
        mock_patch_meta.assert_not_called()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.em_cli.gl.prusalink_upload")
    @patch("filament_calibrator.em_cli.gl.save")
    @patch("filament_calibrator.em_cli.gl.load")
    @patch("filament_calibrator.em_cli.slice_em_specimen")
    @patch("filament_calibrator.em_cli.generate_em_cube_stl")
    def test_upload_verbose(
        self, mock_gen, mock_slice, mock_load, mock_save, mock_upload,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "cube.stl")
        mock_slice.return_value = MagicMock(ok=True, cmd=["ps"], stdout="", stderr="")
        mock_load.return_value = MagicMock(lines=[])
        mock_upload.return_value = "cube.gcode"

        args = self._make_args(
            tmp_path,
            no_upload=False,
            printer_url="http://192.168.1.100",
            api_key="key123",
            verbose=True,
        )
        run(args)

        out = capsys.readouterr().out
        assert "[DEBUG] Upload target:" in out

    @patch("gcode_lib.resolve_printer", side_effect=ValueError("Unknown printer 'NOPE'"))
    def test_invalid_printer_exits(self, mock_resolve, tmp_path):
        """resolve_printer raising ValueError triggers sys.exit."""
        args = self._make_args(tmp_path, printer="NOPE")
        with pytest.raises(SystemExit):
            run(args)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("filament_calibrator.em_cli.run")
    def test_parses_and_runs(self, mock_run):
        main(["--no-upload"])
        mock_run.assert_called_once()
        ns = mock_run.call_args[0][0]
        assert ns.filament_type == "PLA"
        assert ns.no_upload is True

    @patch("filament_calibrator.em_cli.run")
    def test_verbose_flag(self, mock_run):
        main(["--no-upload", "-v"])
        ns = mock_run.call_args[0][0]
        assert ns.verbose is True
