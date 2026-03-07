"""Tests for filament_calibrator.cli — CLI orchestration."""
from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

import gcode_lib as gl

from filament_calibrator.cli import (
    _ARGPARSE_DEFAULTS,
    _UNSET,
    _KNOWN_TYPES,
    MAX_PRINT_TEMP,
    MIN_PRINT_TEMP,
    _apply_config,
    _compute_num_tiers,
    _explicit_keys,
    _patch_m862_nozzle_flags,
    build_parser,
    main,
    _resolve_preset,
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
        assert args.start_temp is _UNSET
        assert args.end_temp is _UNSET
        assert args.temp_step == 5
        assert args.filament_type == "PLA"
        assert args.brand_top == ""
        assert args.brand_bottom == ""
        assert args.nozzle_size == 0.4
        assert args.nozzle_high_flow is False
        assert args.nozzle_hardened is False
        assert args.bed_temp is _UNSET
        assert args.fan_speed is _UNSET
        assert args.config_ini is None
        assert args.prusaslicer_path is None
        assert args.extra_slicer_args is None
        assert args.bed_center is None
        assert args.printer_url is None
        assert args.api_key is None
        assert args.no_upload is False
        assert args.print_after_upload is False
        assert args.output_dir is None
        assert args.keep_files is False
        assert args.ascii_gcode is False
        assert args.verbose is False

    def test_config_flag_default(self):
        p = build_parser()
        args = p.parse_args([])
        assert args.config is None

    def test_config_flag_explicit(self):
        p = build_parser()
        args = p.parse_args(["--config", "/path/to/config.toml"])
        assert args.config == "/path/to/config.toml"

    def test_all_options(self):
        p = build_parser()
        # --extra-slicer-args must come last because nargs=REMAINDER consumes
        # everything after it
        args = p.parse_args([
            "--start-temp", "250",
            "--end-temp", "220",
            "--temp-step", "5",
            "--filament-type", "PETG",
            "--brand-top", "BrandA",
            "--brand-bottom", "BrandB",
            "--nozzle-size", "0.6",
            "--bed-temp", "85",
            "--fan-speed", "30",
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
        assert args.start_temp == 250
        assert args.end_temp == 220
        assert args.temp_step == 5
        assert args.filament_type == "PETG"
        assert args.brand_top == "BrandA"
        assert args.brand_bottom == "BrandB"
        assert args.nozzle_size == 0.6
        assert args.bed_temp == 85
        assert args.fan_speed == 30
        assert args.config_ini == "/path/to/config.ini"
        assert args.prusaslicer_path == "/usr/bin/ps"
        assert args.bed_center == "90,90"
        assert args.extra_slicer_args == ["--nozzle-diameter", "0.4"]
        assert args.printer_url == "http://10.0.0.1"
        assert args.api_key == "test-key"
        assert args.no_upload is True
        assert args.print_after_upload is True
        assert args.output_dir == "/tmp/out"
        assert args.keep_files is True
        assert args.verbose is True
        assert args.config == "/path/to/config.toml"

    def test_known_types(self):
        """_KNOWN_TYPES lists sorted preset names from gcode-lib."""
        assert "ABS" in _KNOWN_TYPES
        assert "PLA" in _KNOWN_TYPES
        assert "PETG" in _KNOWN_TYPES
        assert _KNOWN_TYPES == sorted(_KNOWN_TYPES)


# ---------------------------------------------------------------------------
# _apply_config
# ---------------------------------------------------------------------------


class TestApplyConfig:
    def test_applies_config_to_defaults(self):
        args = argparse.Namespace(
            printer_url=None, api_key=None, prusaslicer_path=None,
            config_ini=None, filament_type="PLA", output_dir=None,
            bed_center=None, nozzle_size=0.4,
        )
        config = {
            "printer_url": "http://10.0.0.1",
            "api_key": "secret",
            "output_dir": "/tmp/out",
        }
        _apply_config(args, config)
        assert args.printer_url == "http://10.0.0.1"
        assert args.api_key == "secret"
        assert args.output_dir == "/tmp/out"

    def test_cli_overrides_config(self):
        args = argparse.Namespace(
            printer_url="http://cli.local", api_key=None,
            prusaslicer_path=None, config_ini=None,
            filament_type="PETG", output_dir=None,
            bed_center=None,
        )
        config = {
            "printer_url": "http://toml.local",
            "filament_type": "ABS",
        }
        _apply_config(args, config)
        # CLI value "http://cli.local" wins over TOML
        assert args.printer_url == "http://cli.local"
        # CLI value "PETG" != default "PLA", so it wins
        assert args.filament_type == "PETG"

    def test_ignores_unknown_keys(self):
        args = argparse.Namespace(
            printer_url=None, api_key=None, prusaslicer_path=None,
            config_ini=None, filament_type="PLA", output_dir=None,
            bed_center=None,
        )
        config = {"unknown_key": "value"}
        _apply_config(args, config)
        assert not hasattr(args, "unknown_key")

    def test_empty_config(self):
        args = argparse.Namespace(
            printer_url=None, api_key=None, prusaslicer_path=None,
            config_ini=None, filament_type="PLA", output_dir=None,
            bed_center=None,
        )
        _apply_config(args, {})
        assert args.printer_url is None
        assert args.filament_type == "PLA"

    def test_all_keys_applied(self):
        args = argparse.Namespace(
            printer_url=None, api_key=None, prusaslicer_path=None,
            config_ini=None, filament_type="PLA", output_dir=None,
            bed_center=None, nozzle_size=0.4,
        )
        config = {
            "printer_url": "http://10.0.0.1",
            "api_key": "key",
            "prusaslicer_path": "/usr/bin/ps",
            "config_ini": "/path/to/profile.ini",
            "filament_type": "ABS",
            "output_dir": "/tmp/out",
            "bed_center": "90,90",
            "nozzle_size": 0.6,
        }
        _apply_config(args, config)
        assert args.printer_url == "http://10.0.0.1"
        assert args.api_key == "key"
        assert args.prusaslicer_path == "/usr/bin/ps"
        assert args.config_ini == "/path/to/profile.ini"
        assert args.filament_type == "ABS"
        assert args.output_dir == "/tmp/out"
        assert args.bed_center == "90,90"
        assert args.nozzle_size == 0.6


    def test_explicit_keys_prevents_overwrite_of_default_value(self):
        """Explicit CLI value matching default is NOT overwritten by TOML."""
        args = argparse.Namespace(
            printer_url=None, api_key=None, prusaslicer_path=None,
            config_ini=None, filament_type="PLA", output_dir=None,
            bed_center=None, nozzle_size=0.4,
            printer="COREONE",
        )
        config = {
            "printer": "MINI",
            "filament_type": "ABS",
        }
        # With explicit_keys telling us "printer" was explicitly set,
        # TOML must not overwrite it — even though it matches the default.
        _apply_config(args, config, explicit_keys=frozenset({"printer"}))
        assert args.printer == "COREONE"
        # filament_type was NOT in explicit_keys and equals the default,
        # so TOML's "ABS" should be applied.
        assert args.filament_type == "ABS"

    def test_explicit_keys_none_falls_back(self):
        """When explicit_keys is None, legacy heuristic is used."""
        args = argparse.Namespace(
            printer_url=None, api_key=None, prusaslicer_path=None,
            config_ini=None, filament_type="PLA", output_dir=None,
            bed_center=None, nozzle_size=0.4,
            printer="COREONE",
        )
        config = {"printer": "MINI"}
        _apply_config(args, config, explicit_keys=None)
        # Legacy: current == default → overwritten
        assert args.printer == "MINI"


# ---------------------------------------------------------------------------
# _explicit_keys
# ---------------------------------------------------------------------------


class TestExplicitKeys:
    def test_detects_supplied_args(self):
        parser = build_parser()
        keys = _explicit_keys(parser, ["--printer", "MINI", "--no-upload"])
        assert "printer" in keys
        assert "no_upload" in keys

    def test_unsupplied_args_excluded(self):
        parser = build_parser()
        keys = _explicit_keys(parser, ["--no-upload"])
        assert "printer" not in keys
        assert "filament_type" not in keys

    def test_default_value_still_detected(self):
        """Even if user types --printer COREONE (the default), it's detected."""
        parser = build_parser()
        keys = _explicit_keys(parser, ["--printer", "COREONE"])
        assert "printer" in keys

    def test_empty_argv(self):
        parser = build_parser()
        keys = _explicit_keys(parser, [])
        # Only argparse-injected defaults; no user-supplied options
        assert "printer" not in keys
        assert "filament_type" not in keys


class TestArgparseDefaults:
    def test_covers_config_keys(self):
        """_ARGPARSE_DEFAULTS has an entry for every config-eligible key."""
        from filament_calibrator.config import _KEY_TO_ATTR
        for attr in _KEY_TO_ATTR.values():
            assert attr in _ARGPARSE_DEFAULTS


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
        assert "filament-calibrator" in str(result)

    def test_custom_prefix(self):
        result = _resolve_output_dir(None, prefix="pressure-advance-")
        assert result.exists()
        assert "pressure-advance-" in str(result)


# ---------------------------------------------------------------------------
# _patch_m862_nozzle_flags
# ---------------------------------------------------------------------------


class TestPatchM862NozzleFlags:
    def test_no_flags(self):
        lines = ["M862.1 P0.4", "G28"]
        result = _patch_m862_nozzle_flags(lines)
        assert result == ["M862.1 P0.4 A0 F0", "G28"]

    def test_hardened_only(self):
        lines = ["M862.1 P0.4"]
        result = _patch_m862_nozzle_flags(lines, nozzle_hardened=True)
        assert result == ["M862.1 P0.4 A1 F0"]

    def test_high_flow_only(self):
        lines = ["M862.1 P0.6"]
        result = _patch_m862_nozzle_flags(lines, nozzle_high_flow=True)
        assert result == ["M862.1 P0.6 A0 F1"]

    def test_both_flags(self):
        lines = ["M862.1 P0.4"]
        result = _patch_m862_nozzle_flags(
            lines, nozzle_hardened=True, nozzle_high_flow=True,
        )
        assert result == ["M862.1 P0.4 A1 F1"]

    def test_no_m862_lines(self):
        lines = ["G28", "G1 X10 Y10", "M104 S200"]
        result = _patch_m862_nozzle_flags(lines)
        assert result == lines

    def test_idempotent_repatch(self):
        lines = ["M862.1 P0.4 A0 F0"]
        result = _patch_m862_nozzle_flags(
            lines, nozzle_hardened=True, nozzle_high_flow=True,
        )
        assert result == ["M862.1 P0.4 A1 F1"]

    def test_preserves_trailing_comment(self):
        lines = ["M862.1 P0.4 ; nozzle check"]
        result = _patch_m862_nozzle_flags(lines, nozzle_hardened=True)
        assert result == ["M862.1 P0.4 A1 F0 ; nozzle check"]

    def test_empty_lines(self):
        result = _patch_m862_nozzle_flags([])
        assert result == []


# ---------------------------------------------------------------------------
# _resolve_preset
# ---------------------------------------------------------------------------


class TestResolvePreset:
    def test_pla_defaults(self):
        """PLA preset: temp_max=230, temp_min=190, bed=60, fan=100."""
        args = argparse.Namespace(
            filament_type="PLA", start_temp=_UNSET, end_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 230
        assert r["end_temp"] == 190
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100

    def test_petg_defaults(self):
        """PETG preset: temp_max=260, temp_min=220, bed=80, fan=40."""
        args = argparse.Namespace(
            filament_type="PETG", start_temp=_UNSET, end_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 260
        assert r["end_temp"] == 220
        assert r["bed_temp"] == 80
        assert r["fan_speed"] == 40

    def test_abs_defaults(self):
        """ABS preset: temp_max=270, temp_min=230, bed=100, fan=20."""
        args = argparse.Namespace(
            filament_type="ABS", start_temp=_UNSET, end_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 270
        assert r["end_temp"] == 230
        assert r["bed_temp"] == 100
        assert r["fan_speed"] == 20

    def test_case_insensitive(self):
        """Filament type lookup is case-insensitive."""
        args = argparse.Namespace(
            filament_type="pla", start_temp=_UNSET, end_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 230
        assert r["end_temp"] == 190
        assert r["bed_temp"] == 60

    def test_unknown_filament_uses_fallback(self):
        """Unknown filament type uses conservative defaults."""
        args = argparse.Namespace(
            filament_type="EXOTIC", start_temp=_UNSET, end_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 230
        assert r["end_temp"] == 190
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100

    def test_explicit_start_temp_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PLA", start_temp=240, end_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 240
        assert r["end_temp"] == 190  # still from preset
        assert r["bed_temp"] == 60
        assert r["fan_speed"] == 100

    def test_explicit_end_temp_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PLA", start_temp=_UNSET, end_temp=200,
            bed_temp=_UNSET, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 230  # still from preset
        assert r["end_temp"] == 200

    def test_explicit_bed_temp_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PETG", start_temp=_UNSET, end_temp=_UNSET,
            bed_temp=90, fan_speed=_UNSET,
        )
        r = _resolve_preset(args)
        assert r["bed_temp"] == 90
        assert r["fan_speed"] == 40  # still from preset

    def test_explicit_fan_speed_overrides_preset(self):
        args = argparse.Namespace(
            filament_type="PLA", start_temp=_UNSET, end_temp=_UNSET,
            bed_temp=_UNSET, fan_speed=50,
        )
        r = _resolve_preset(args)
        assert r["fan_speed"] == 50
        assert r["bed_temp"] == 60  # still from preset

    def test_all_explicit_overrides(self):
        """When all values are explicit, preset is ignored."""
        args = argparse.Namespace(
            filament_type="PLA", start_temp=250, end_temp=200,
            bed_temp=70, fan_speed=80,
        )
        r = _resolve_preset(args)
        assert r["start_temp"] == 250
        assert r["end_temp"] == 200
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

    def test_start_equals_end_exits(self):
        with pytest.raises(SystemExit):
            _compute_num_tiers(200, 200, 5)

    def test_start_less_than_end_exits(self):
        with pytest.raises(SystemExit):
            _compute_num_tiers(190, 200, 5)

    def test_not_divisible_exits(self):
        # 230→190 = 40, not divisible by 7
        with pytest.raises(SystemExit):
            _compute_num_tiers(230, 190, 7)

    def test_ten_tiers_allowed(self):
        # 250→200 step 5 → 11 (too many), but 245→200 step 5 → 10 (ok)
        assert _compute_num_tiers(245, 200, 5) == 10

    def test_temp_step_zero_exits(self):
        with pytest.raises(SystemExit, match="--temp-step must be positive"):
            _compute_num_tiers(230, 200, 0)

    def test_temp_step_negative_exits(self):
        with pytest.raises(SystemExit, match="--temp-step must be positive"):
            _compute_num_tiers(230, 200, -5)

    def test_start_temp_below_min_exits(self):
        with pytest.raises(SystemExit, match="outside the normal printing range"):
            _compute_num_tiers(140, 130, 5)

    def test_start_temp_above_max_exits(self):
        with pytest.raises(SystemExit, match="outside the normal printing range"):
            _compute_num_tiers(360, 340, 5)

    def test_end_temp_below_min_exits(self):
        with pytest.raises(SystemExit, match="outside the normal printing range"):
            _compute_num_tiers(160, 140, 5)

    def test_end_temp_above_max_exits(self):
        with pytest.raises(SystemExit, match="outside the normal printing range"):
            _compute_num_tiers(MAX_PRINT_TEMP, MAX_PRINT_TEMP + 10, 5)

    def test_boundary_temps_allowed(self):
        # Exactly at MIN and MAX boundaries should be valid
        assert _compute_num_tiers(MIN_PRINT_TEMP + 10, MIN_PRINT_TEMP, 5) == 3
        assert _compute_num_tiers(MAX_PRINT_TEMP, MAX_PRINT_TEMP - 10, 5) == 3

    def test_range_smaller_than_step_exits(self):
        # 205→200 = 5°C range, but step is 10 → range too small
        with pytest.raises(SystemExit, match="at least --end-temp \\+ --temp-step"):
            _compute_num_tiers(205, 200, 10)

    def test_print_range_constants(self):
        assert MIN_PRINT_TEMP == 150
        assert MAX_PRINT_TEMP == 350


class TestBuildTowerConfig:
    def test_maps_args(self):
        args = argparse.Namespace(
            temp_step=5,
            filament_type="PETG", brand_top="X", brand_bottom="Y",
        )
        config = _build_tower_config(args, start_temp=250, end_temp=220)
        assert isinstance(config, TowerConfig)
        assert config.start_temp == 250
        assert config.temp_step == 5
        assert config.num_tiers == 7  # (250-220)/5 + 1 = 7
        assert config.filament_type == "PETG"
        assert config.brand_top == "X"
        assert config.brand_bottom == "Y"


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
            start_temp=_UNSET, end_temp=_UNSET, temp_step=5,
            filament_type="PLA", brand_top="", brand_bottom="",
            nozzle_size=0.4,
            nozzle_high_flow=False, nozzle_hardened=False,
            bed_temp=_UNSET, fan_speed=_UNSET,
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
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_full_pipeline_no_upload(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
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
        # PLA preset: start_temp = temp_max = 230
        assert slice_kwargs["nozzle_temp"] == 230
        assert slice_kwargs["bed_temp"] == 60   # PLA preset
        assert slice_kwargs["fan_speed"] == 100  # PLA preset
        mock_tiers.assert_called_once()
        mock_load.assert_called_once()
        mock_insert.assert_called_once()
        mock_save.assert_called_once()

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_slicer_failure_exits(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
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
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.prusalink_upload")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_upload(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, mock_upload,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
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

    @patch("filament_calibrator.cli.load_config", return_value={})
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_upload_missing_url_exits(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, mock_load_config, tmp_path
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_keep_files(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        # PLA preset: high=230, low=190, jump=5 → 9 tiers
        stl = tmp_path / "temp_tower_PLA_230_5x9_abc12.stl"
        raw_gcode = tmp_path / "temp_tower_PLA_230_5x9_abc12_raw.bgcode"
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_no_keep_files_cleans_up(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        stl = tmp_path / "temp_tower_PLA_230_5x9_abc12.stl"
        raw_gcode = tmp_path / "temp_tower_PLA_230_5x9_abc12_raw.bgcode"
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_explicit_overrides_passed_to_slicer(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
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

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_config_file_applies_defaults(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        # Write a TOML config that sets filament-type to PETG
        cfg = tmp_path / "test.toml"
        cfg.write_text('filament-type = "PETG"\n')

        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, config=str(cfg))
        run(args)

        # filament_type should be PETG from config (overriding PLA default)
        gen_call = mock_gen.call_args
        tower_config = gen_call[0][0]
        assert tower_config.filament_type == "PETG"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_cli_overrides_config_file(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        cfg = tmp_path / "test.toml"
        cfg.write_text('filament-type = "PETG"\n')

        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        # CLI explicitly sets filament_type to ABS, should override TOML's PETG
        args = self._make_args(
            tmp_path, config=str(cfg), filament_type="ABS",
        )
        run(args)

        gen_call = mock_gen.call_args
        tower_config = gen_call[0][0]
        assert tower_config.filament_type == "ABS"

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_bed_center_passed_to_slicer(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, bed_center="90,90")
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["bed_center"] == "90,90"

    @patch("filament_calibrator.cli.load_config", return_value={})
    @patch("filament_calibrator.cli._find_config_path", return_value=None)
    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_verbose_output(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta,
        mock_find_config, mock_load_config, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer", "--slice"], stdout="", stderr=""
        )
        mock_tiers.return_value = [
            MagicMock(z_start=0.0, z_end=10.0, temp=230),
        ]
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True)
        run(args)

        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out
        assert "No config file loaded" in captured.out
        assert "Filament preset 'PLA' found" in captured.out
        assert "start_temp=230" in captured.out
        assert "Bed center:" in captured.out
        assert "PrusaSlicer command:" in captured.out
        assert "Temperature tiers:" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_verbose_shows_slicer_stdout(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"],
            stdout="Slicing complete in 3.2s", stderr=""
        )
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True)
        run(args)

        captured = capsys.readouterr()
        assert "PrusaSlicer stdout: Slicing complete in 3.2s" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_no_verbose_no_debug(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=False)
        run(args)

        captured = capsys.readouterr()
        assert "[DEBUG]" not in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_verbose_shows_config_file(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        cfg = tmp_path / "test.toml"
        cfg.write_text('filament-type = "PLA"\n')

        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True, config=str(cfg))
        run(args)

        captured = capsys.readouterr()
        assert "Config file:" in captured.out
        assert str(cfg) in captured.out
        assert "Config values:" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.prusalink_upload")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_verbose_upload(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save, mock_upload,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_tiers.return_value = []
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
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_verbose_unknown_filament(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path, capsys
    ):
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(
            ok=True, cmd=["prusa-slicer"], stdout="", stderr=""
        )
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, verbose=True, filament_type="EXOTIC")
        run(args)

        captured = capsys.readouterr()
        assert "not in presets" in captured.out
        assert "fallback defaults" in captured.out

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_ascii_gcode_uses_gcode_extension(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        """--ascii-gcode uses .gcode extension for filenames."""
        stl = tmp_path / "temp_tower_PLA_230_5x9_abc12.stl"
        raw_gcode = tmp_path / "temp_tower_PLA_230_5x9_abc12_raw.gcode"
        stl.write_text("dummy")
        raw_gcode.write_text("dummy")

        mock_gen.return_value = str(stl)
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, ascii_gcode=True, keep_files=True)
        run(args)

        # Raw gcode path should end with _raw.gcode
        raw_path = mock_load.call_args[0][0]
        assert raw_path.endswith("_raw.gcode")
        # Final gcode path should end with .gcode
        save_path = mock_save.call_args[0][1]
        assert save_path.endswith(".gcode")
        assert not save_path.endswith(".bgcode")

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_binary_gcode_passed_to_slicer(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        """binary_gcode=True is passed to slice_tower by default."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path)
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["binary_gcode"] is True

    @patch("gcode_lib.patch_slicer_metadata")
    @patch("gcode_lib.inject_thumbnails")
    @patch("gcode_lib.compute_bed_shape", return_value="0x0,250x0,250x220,0x220")
    @patch("gcode_lib.compute_bed_center", return_value="125,110")
    @patch("gcode_lib.resolve_printer", return_value="COREONE")
    @patch("filament_calibrator.cli.gl.save")
    @patch("filament_calibrator.cli.gl.load")
    @patch("filament_calibrator.cli.insert_temperatures")
    @patch("filament_calibrator.cli.compute_temp_tiers")
    @patch("filament_calibrator.cli.slice_tower")
    @patch("filament_calibrator.cli.generate_tower_stl")
    def test_ascii_gcode_passes_false_to_slicer(
        self, mock_gen, mock_slice, mock_tiers,
        mock_insert, mock_load, mock_save,
        mock_resolve, mock_center, mock_shape,
        mock_inject, mock_patch_meta, tmp_path
    ):
        """--ascii-gcode sets binary_gcode=False in slice_tower call."""
        mock_gen.return_value = str(tmp_path / "tower.stl")
        mock_slice.return_value = MagicMock(ok=True)
        mock_tiers.return_value = []
        mock_load.return_value = MagicMock(lines=[])
        mock_insert.return_value = []

        args = self._make_args(tmp_path, ascii_gcode=True)
        run(args)

        slice_kwargs = mock_slice.call_args[1]
        assert slice_kwargs["binary_gcode"] is False

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
    @patch("filament_calibrator.cli.run")
    def test_parses_and_runs(self, mock_run):
        main(["--no-upload", "--start-temp", "200"])
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.start_temp == 200
        assert args.no_upload is True

    @patch("filament_calibrator.cli.run")
    def test_defaults(self, mock_run):
        main([])
        args = mock_run.call_args[0][0]
        assert args.start_temp is _UNSET
        assert args.end_temp is _UNSET

    @patch("filament_calibrator.cli.run")
    def test_bed_temp_and_fan_speed(self, mock_run):
        main(["--bed-temp", "90", "--fan-speed", "60"])
        args = mock_run.call_args[0][0]
        assert args.bed_temp == 90
        assert args.fan_speed == 60

    @patch("filament_calibrator.cli.run")
    def test_bed_center(self, mock_run):
        main(["--bed-center", "90,90"])
        args = mock_run.call_args[0][0]
        assert args.bed_center == "90,90"

    @patch("filament_calibrator.cli.run")
    def test_verbose_flag(self, mock_run):
        main(["-v"])
        args = mock_run.call_args[0][0]
        assert args.verbose is True

    @patch("filament_calibrator.cli.run")
    def test_verbose_long_flag(self, mock_run):
        main(["--verbose"])
        args = mock_run.call_args[0][0]
        assert args.verbose is True


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
