"""Tests for filament_calibrator.pa_cli — pressure advance CLI orchestration."""
from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

import gcode_lib as gl

from filament_calibrator.cli import _KNOWN_TYPES, _UNSET
from filament_calibrator.pa_cli import (
    MAX_LEVELS,
    METHOD_CHOICES,
    _parse_bed_center_x,
    _validate_pa_args,
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
            p.parse_args([])  # missing required --start-pa etc.

    def test_defaults(self):
        p = build_parser()
        args = p.parse_args(["--start-pa", "0", "--end-pa", "0.1", "--pa-step", "0.01"])
        assert args.start_pa == 0.0
        assert args.end_pa == 0.1
        assert args.pa_step == 0.01
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
            "--start-pa", "0.02",
            "--end-pa", "0.1",
            "--pa-step", "0.02",
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
            "--output-dir", "/tmp/pa",
            "--keep-files",
            "-v",
        ])
        assert args.start_pa == 0.02
        assert args.end_pa == 0.1
        assert args.pa_step == 0.02
        assert args.level_height == 2.0
        assert args.filament_type == "PETG"
        assert args.nozzle_size == 0.6
        assert args.layer_height == 0.3
        assert args.extrusion_width == 0.68
        assert args.bed_temp == 80
        assert args.fan_speed == 50
        assert args.nozzle_temp == 240
        assert args.verbose is True

    def test_method_default(self):
        p = build_parser()
        args = p.parse_args(["--start-pa", "0", "--end-pa", "0.1", "--pa-step", "0.01"])
        assert args.method == "tower"

    def test_method_pattern(self):
        p = build_parser()
        args = p.parse_args([
            "--start-pa", "0", "--end-pa", "0.1", "--pa-step", "0.01",
            "--method", "pattern",
        ])
        assert args.method == "pattern"

    def test_method_invalid(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args([
                "--start-pa", "0", "--end-pa", "0.1", "--pa-step", "0.01",
                "--method", "invalid",
            ])

    def test_method_choices_constant(self):
        assert METHOD_CHOICES == ("tower", "pattern")

    def test_pattern_options_defaults(self):
        p = build_parser()
        args = p.parse_args(["--start-pa", "0", "--end-pa", "0.1", "--pa-step", "0.01"])
        assert args.corner_angle == 90.0
        assert args.arm_length == 40.0
        assert args.frame_offset == 0.0
        assert args.wall_count == 3
        assert args.num_layers == 4
        assert args.frame_layers == 1
        assert args.pattern_spacing == 1.6

    def test_pattern_options_custom(self):
        p = build_parser()
        args = p.parse_args([
            "--start-pa", "0", "--end-pa", "0.1", "--pa-step", "0.01",
            "--method", "pattern",
            "--corner-angle", "60",
            "--arm-length", "20",
            "--frame-offset", "5",
            "--wall-count", "5",
            "--num-layers", "8",
            "--frame-layers", "2",
            "--pattern-spacing", "3",
        ])
        assert args.corner_angle == 60.0
        assert args.arm_length == 20.0
        assert args.frame_offset == 5.0
        assert args.wall_count == 5
        assert args.num_layers == 8
        assert args.frame_layers == 2
        assert args.pattern_spacing == 3.0

    def test_filament_type_help_lists_presets(self):
        p = build_parser()
        # The help text should contain known filament types
        help_text = p.format_help()
        assert "PLA" in help_text


# ---------------------------------------------------------------------------
# _validate_pa_args
# ---------------------------------------------------------------------------


class TestValidatePAArgs:
    def test_valid_range(self):
        assert _validate_pa_args(0.0, 0.1, 0.02) == 6

    def test_start_pa_zero_is_valid(self):
        """PA value of 0.0 is valid (unlike flow speeds)."""
        num = _validate_pa_args(0.0, 0.05, 0.05)
        assert num == 2

    def test_start_pa_negative_exits(self):
        with pytest.raises(SystemExit, match="non-negative"):
            _validate_pa_args(-0.1, 0.1, 0.02)

    def test_pa_step_zero_exits(self):
        with pytest.raises(SystemExit, match="positive"):
            _validate_pa_args(0.0, 0.1, 0.0)

    def test_pa_step_negative_exits(self):
        with pytest.raises(SystemExit, match="positive"):
            _validate_pa_args(0.0, 0.1, -0.01)

    def test_level_height_zero_exits(self):
        with pytest.raises(SystemExit, match="--level-height must be positive"):
            _validate_pa_args(0.0, 0.1, 0.01, 0.0)

    def test_level_height_negative_exits(self):
        with pytest.raises(SystemExit, match="--level-height must be positive"):
            _validate_pa_args(0.0, 0.1, 0.01, -1.0)

    def test_end_pa_equal_exits(self):
        with pytest.raises(SystemExit, match="greater than"):
            _validate_pa_args(0.1, 0.1, 0.01)

    def test_end_pa_less_exits(self):
        with pytest.raises(SystemExit, match="greater than"):
            _validate_pa_args(0.1, 0.05, 0.01)

    def test_not_divisible_exits(self):
        with pytest.raises(SystemExit, match="evenly divisible"):
            _validate_pa_args(0.0, 0.1, 0.03)

    def test_too_many_levels_exits(self):
        with pytest.raises(SystemExit, match="exceeds maximum"):
            _validate_pa_args(0.0, 5.1, 0.1)

    def test_max_levels_constant(self):
        assert MAX_LEVELS == 50


# ---------------------------------------------------------------------------
# _parse_bed_center_x
# ---------------------------------------------------------------------------


class TestParseBedCenterX:
    def test_valid_format(self):
        assert _parse_bed_center_x("125,110") == 125.0

    def test_float_values(self):
        assert _parse_bed_center_x("125.5,110.0") == 125.5

    def test_missing_comma_exits(self):
        with pytest.raises(SystemExit, match="X,Y format"):
            _parse_bed_center_x("125")

    def test_too_many_parts_exits(self):
        with pytest.raises(SystemExit, match="X,Y format"):
            _parse_bed_center_x("1,2,3")

    def test_non_numeric_x_exits(self):
        with pytest.raises(SystemExit, match="not a number"):
            _parse_bed_center_x("abc,110")

    def test_empty_string_exits(self):
        with pytest.raises(SystemExit, match="X,Y format"):
            _parse_bed_center_x("")


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
            start_pa=0.0, end_pa=0.1, pa_step=0.1,
            method="tower",
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
            # Pattern-specific defaults (used when method="pattern")
            corner_angle=90.0, arm_length=40.0, frame_offset=0.0,
            wall_count=3, num_layers=4, frame_layers=1, pattern_spacing=1.6,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_full_pipeline_no_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_slicer_failure_exits(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
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
    @patch("filament_calibrator.pa_cli.gl.prusalink_upload")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_upload, mock_inject, mock_patch_meta, tmp_path
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

    @patch("filament_calibrator.pa_cli.load_config", return_value={})
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_keep_files(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        stl = tmp_path / "pa_tower_PLA_0.0_0.1x2_abc12.stl"
        raw_gcode = tmp_path / "pa_tower_PLA_0.0_0.1x2_abc12_raw.bgcode"
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_no_keep_files_cleans_up(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        stl = tmp_path / "pa_tower_PLA_0.0_0.1x2_abc12.stl"
        raw_gcode = tmp_path / "pa_tower_PLA_0.0_0.1x2_abc12_raw.bgcode"
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

    @patch("filament_calibrator.pa_cli.load_config", return_value={})
    @patch("filament_calibrator.pa_cli._find_config_path", return_value=None)
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
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
            MagicMock(z_start=0.0, z_end=1.0, pa_value=0.0),
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
        assert "PA levels:" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_no_verbose_no_debug(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_verbose_shows_slicer_stdout(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_verbose_unknown_filament(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_verbose_shows_config_file(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
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
    @patch("filament_calibrator.pa_cli.gl.prusalink_upload")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_verbose_upload(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_upload, mock_inject, mock_patch_meta, tmp_path, capsys
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_slicer_receives_correct_args(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_preset_temps_passed_to_slicer(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """Filament preset nozzle/bed/fan are forwarded to slice_pa_specimen."""
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_explicit_temps_override_preset(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_config_file_applies_defaults(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
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

    # --- --printer tests ---

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_printer_resolves_and_sets_bed_center(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path
    ):
        """--printer resolves printer name and auto-sets bed center."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\n"
        mock_render_end.return_value = "M104 S0\n"

        args = self._make_args(tmp_path, printer="coreone")
        run(args)

        # bed_center should be auto-set from COREONE preset
        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["bed_center"] == "125,110"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_printer_explicit_bed_center_not_overridden(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path
    ):
        """Explicit --bed-center is NOT overridden by --printer."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\n"
        mock_render_end.return_value = "M104 S0\n"

        args = self._make_args(
            tmp_path, printer="coreone", bed_center="100,100",
        )
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["bed_center"] == "100,100"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_printer_renders_start_end_gcode(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path
    ):
        """--printer renders start/end G-code and passes to slicer."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\nG29\n"
        mock_render_end.return_value = "M104 S0\nG28 X\n"

        args = self._make_args(tmp_path, printer="mk4s")
        run(args)

        mock_render_start.assert_called_once()
        mock_render_end.assert_called_once()
        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["start_gcode"] == "G28\nG29\n"
        assert slice_kwargs["end_gcode"] == "M104 S0\nG28 X\n"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_printer_with_config_ini_skips_gcode_render(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path
    ):
        """--printer with --config-ini does NOT render start/end G-code."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(
            tmp_path, printer="coreone", config_ini="/config.ini",
        )
        run(args)

        mock_render_start.assert_not_called()
        mock_render_end.assert_not_called()
        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["start_gcode"] is None
        assert slice_kwargs["end_gcode"] is None

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_printer_cool_fan_disabled_for_enclosure_filament(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path
    ):
        """cool_fan=False for filaments requiring enclosure (e.g. ABS)."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\n"
        mock_render_end.return_value = "M104 S0\n"

        args = self._make_args(
            tmp_path, printer="coreone", filament_type="ABS",
        )
        run(args)

        render_kwargs = mock_render_start.call_args[1]
        assert render_kwargs["cool_fan"] is False

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_printer_cool_fan_enabled_for_pla(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path
    ):
        """cool_fan=True for PLA (no enclosure required)."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\n"
        mock_render_end.return_value = "M104 S0\n"

        args = self._make_args(
            tmp_path, printer="coreone", filament_type="PLA",
        )
        run(args)

        render_kwargs = mock_render_start.call_args[1]
        assert render_kwargs["cool_fan"] is True

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_printer_cool_fan_true_for_unknown_filament(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path
    ):
        """cool_fan defaults to True for unknown filament types."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\n"
        mock_render_end.return_value = "M104 S0\n"

        args = self._make_args(
            tmp_path, printer="coreone", filament_type="EXOTIC",
        )
        run(args)

        render_kwargs = mock_render_start.call_args[1]
        assert render_kwargs["cool_fan"] is True

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_verbose_printer_debug(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save,
        mock_render_start, mock_render_end, mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        """Verbose mode shows printer debug info and gcode render message."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\n"
        mock_render_end.return_value = "M104 S0\n"

        args = self._make_args(
            tmp_path, printer="coreone", verbose=True,
        )
        run(args)

        captured = capsys.readouterr()
        assert "Printer: COREONE" in captured.out
        assert "bed center: 125,110" in captured.out
        assert "Rendered COREONE start/end G-code" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_pa_lookup_table_printed(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        """PA lookup table is always printed."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = [
            MagicMock(z_start=0.0, z_end=1.0, pa_value=0.0),
            MagicMock(z_start=1.0, z_end=2.0, pa_value=0.05),
        ]
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        captured = capsys.readouterr()
        assert "PA value by height:" in captured.out
        assert "sharpest corners" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_binary_gcode_passed_to_slicer(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """binary_gcode=True is passed to slice_pa_specimen by default."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["binary_gcode"] is True

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_ascii_gcode_passes_false_to_slicer(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """--ascii-gcode sets binary_gcode=False in slice_pa_specimen call."""
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
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_levels")
    @patch("filament_calibrator.pa_cli.slice_pa_specimen")
    @patch("filament_calibrator.pa_cli.generate_pa_tower_stl")
    def test_ascii_gcode_uses_gcode_extension(
        self, mock_gen, mock_slice, mock_levels,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """--ascii-gcode uses .gcode extension for filenames."""
        stl = tmp_path / "pa_tower_PLA_0.0_0.1x2_abc12.stl"
        raw_gcode = tmp_path / "pa_tower_PLA_0.0_0.1x2_abc12_raw.gcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_levels.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, ascii_gcode=True, keep_files=True)
        run(args)

        raw_path = mock_load.call_args[0][0]
        assert raw_path.endswith("_raw.gcode")
        save_path = mock_save.call_args[0][1]
        assert save_path.endswith(".gcode")
        assert not save_path.endswith(".bgcode")

    @patch("gcode_lib.resolve_printer", side_effect=ValueError("Unknown printer 'NOPE'"))
    def test_invalid_printer_exits(self, mock_resolve, tmp_path):
        """resolve_printer raising ValueError triggers sys.exit."""
        args = self._make_args(tmp_path, printer="NOPE")
        with pytest.raises(SystemExit):
            run(args)


# ---------------------------------------------------------------------------
# Pattern pipeline
# ---------------------------------------------------------------------------


class TestRunPattern:
    """Tests for the pattern-method PA calibration pipeline."""

    @pytest.fixture(autouse=True)
    def _fix_suffix(self):
        with patch("gcode_lib.unique_suffix", return_value="abc12"):
            yield

    def _make_args(self, tmp_path, **overrides):
        defaults = dict(
            start_pa=0.0, end_pa=0.1, pa_step=0.1,
            method="pattern",
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
            corner_angle=90.0, arm_length=40.0, frame_offset=0.0,
            wall_count=3, num_layers=4, frame_layers=1, pattern_spacing=1.6,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_pipeline_dispatches(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """method='pattern' dispatches to pattern pipeline, not tower."""
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        mock_gen.assert_called_once()
        mock_slice.assert_called_once()
        mock_regions.assert_called_once()
        mock_insert.assert_called_once()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_tower_functions_not_called(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """Pattern pipeline does not call tower-specific functions."""
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        with patch("filament_calibrator.pa_cli.generate_pa_tower_stl") as mock_tower_gen, \
             patch("filament_calibrator.pa_cli.slice_pa_specimen") as mock_tower_slice:
            run(args)
            mock_tower_gen.assert_not_called()
            mock_tower_slice.assert_not_called()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_slicer_failure_exits(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(
            ok=False, returncode=1, stderr="slice error"
        )

        args = self._make_args(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code == 1

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.prusalink_upload")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_upload(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_upload,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_upload.return_value = "pattern.gcode"

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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_perimeters_passed(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """wall_count is passed as perimeters to slice_pa_pattern."""
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, wall_count=5)
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["perimeters"] == 5

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_x_centers_shifted_by_bed_center(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """Model-space tip X values are shifted by slicer centering translation."""
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [-20.0, 20.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        # Translation is bed_cx - model_bbox_center_x.
        # For mocked tips [-20, 20] with default geometry this is:
        #   x_min ≈ -51.8507, x_max ≈ 24.1321, model_cx ≈ -13.8593
        #   shift ≈ 138.8593, so tips map to ≈ [118.8593, 158.8593].
        region_call_args = mock_regions.call_args[0]
        shifted_centers = region_call_args[1]
        assert shifted_centers == pytest.approx([118.8593, 158.8593], abs=1e-4)

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_custom_bed_center(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        """Custom bed_center uses slicer translation, not direct X addition."""
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, bed_center="100,100")
        run(args)

        region_call_args = mock_regions.call_args[0]
        shifted_centers = region_call_args[1]
        assert shifted_centers == pytest.approx([113.8593], abs=1e-4)

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_verbose_output(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer", "--slice"], stdout="", stderr=""
        )
        mock_regions.return_value = [
            MagicMock(x_start=float("-inf"), x_end=float("inf"), pa_value=0.0),
        ]
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True)
        run(args)

        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out
        assert "PA pattern:" in captured.out
        assert "Chevron:" in captured.out
        assert "PA regions:" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_reference_table_printed(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [125.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        captured = capsys.readouterr()
        assert "PA value by pattern position:" in captured.out
        assert "sharpest corners" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_keep_files(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        stl = tmp_path / "pa_pattern_PLA_0.0_0.1x2_abc12.stl"
        raw_gcode = tmp_path / "pa_pattern_PLA_0.0_0.1x2_abc12_raw.bgcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = (str(stl), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, keep_files=True)
        run(args)

        assert stl.exists()
        assert raw_gcode.exists()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_no_keep_files_cleans_up(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path
    ):
        stl = tmp_path / "pa_pattern_PLA_0.0_0.1x2_abc12.stl"
        raw_gcode = tmp_path / "pa_pattern_PLA_0.0_0.1x2_abc12_raw.bgcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = (str(stl), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, keep_files=False)
        run(args)

        assert not stl.exists()
        assert not raw_gcode.exists()

    @patch("gcode_lib.render_end_gcode")
    @patch("gcode_lib.render_start_gcode")
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_printer_renders_gcode(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save,
        mock_inject, mock_patch_meta,
        mock_render_start, mock_render_end, tmp_path
    ):
        """--printer renders start/end G-code for pattern pipeline."""
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(ok=True)
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []
        mock_render_start.return_value = "G28\n"
        mock_render_end.return_value = "M104 S0\n"

        args = self._make_args(tmp_path, printer="mk4s")
        run(args)

        mock_render_start.assert_called_once()
        mock_render_end.assert_called_once()
        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["start_gcode"] == "G28\n"
        assert slice_kwargs["end_gcode"] == "M104 S0\n"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("filament_calibrator.pa_cli.gl.save")
    @patch("filament_calibrator.pa_cli.gl.load")
    @patch("filament_calibrator.pa_cli.insert_pa_pattern_commands")
    @patch("filament_calibrator.pa_cli.compute_pa_pattern_regions")
    @patch("filament_calibrator.pa_cli.slice_pa_pattern")
    @patch("filament_calibrator.pa_cli.generate_pa_pattern_stl")
    def test_pattern_verbose_slicer_stdout(
        self, mock_gen, mock_slice, mock_regions,
        mock_insert, mock_load, mock_save, mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = (str(tmp_path / "pattern.stl"), [0.0])
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"],
            stdout="Slicing done", stderr=""
        )
        mock_regions.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True)
        run(args)

        captured = capsys.readouterr()
        assert "PrusaSlicer stdout: Slicing done" in captured.out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("filament_calibrator.pa_cli.run")
    def test_parses_and_runs(self, mock_run):
        main(["--start-pa", "0", "--end-pa", "0.1",
              "--pa-step", "0.01", "--no-upload"])
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.start_pa == 0.0
        assert args.end_pa == 0.1
        assert args.pa_step == 0.01
        assert args.no_upload is True

    @patch("filament_calibrator.pa_cli.run")
    def test_verbose_flag(self, mock_run):
        main(["--start-pa", "0", "--end-pa", "0.1",
              "--pa-step", "0.05", "-v"])
        args = mock_run.call_args[0][0]
        assert args.verbose is True
