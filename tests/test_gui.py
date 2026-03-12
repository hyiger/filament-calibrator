"""Tests for filament_calibrator.gui helper functions."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import gcode_lib as gl

from filament_calibrator.cli import _apply_config
from filament_calibrator.gui import (
    _FALLBACK_PRESET,
    _NOZZLE_SIZES,
    _PRINTER_LIST,
    _RESULTS_STATE_MAPPING,
    _check_printer_temps,
    _clean_path,
    _fresh_output_dir,
    _is_frozen,
    _open_directory_dialog,
    _open_file_dialog,
    _osascript_directory_dialog,
    _osascript_file_dialog,
    _results_file_path,
    _results_key,
    _run_osascript,
    _tkinter_directory_dialog,
    _tkinter_file_dialog,
    _win32_directory_dialog,
    _win32_file_dialog,
    apply_ini_to_session,
    apply_saved_results_to_session,
    apply_toml_to_session,
    build_calibration_results,
    build_bridge_namespace,
    build_cooling_namespace,
    build_em_namespace,
    build_flow_namespace,
    build_overhang_namespace,
    build_pa_namespace,
    build_retraction_namespace,
    build_retraction_speed_namespace,
    build_shrinkage_namespace,
    build_temp_tower_namespace,
    build_tolerance_namespace,
    find_output_file,
    get_preset,
    load_saved_results,
    results_to_dict,
    run_pipeline,
    save_results,
    snap_nozzle_size,
    upload_to_printer,
)


# ---------------------------------------------------------------------------
# get_preset
# ---------------------------------------------------------------------------

class TestGetPreset:
    """Test get_preset() with known and unknown filament types."""

    def test_known_pla(self) -> None:
        p = get_preset("PLA")
        assert p["hotend"] == 215
        assert p["bed"] == 60
        assert p["fan"] == 100
        assert p["temp_min"] == 190
        assert p["temp_max"] == 230
        assert p["enclosure"] is False

    def test_known_abs(self) -> None:
        p = get_preset("ABS")
        assert p["hotend"] == 255
        assert p["bed"] == 100
        assert p["enclosure"] is True

    def test_case_insensitive(self) -> None:
        p = get_preset("petg")
        assert p["hotend"] == 240

    def test_unknown_type(self) -> None:
        p = get_preset("UNKNOWN_MATERIAL")
        assert p == _FALLBACK_PRESET
        # Must be a copy, not the original dict.
        assert p is not _FALLBACK_PRESET


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Test run_pipeline() stdout capture and error handling."""

    def test_success(self) -> None:
        def _ok(args: argparse.Namespace) -> None:
            print("step 1")
            print("step 2")

        success, output = run_pipeline(_ok, argparse.Namespace())
        assert success is True
        assert "step 1" in output
        assert "step 2" in output

    def test_sys_exit_zero(self) -> None:
        def _exit_zero(_: argparse.Namespace) -> None:
            print("before exit")
            sys.exit(0)

        success, output = run_pipeline(_exit_zero, argparse.Namespace())
        assert success is True
        assert "before exit" in output

    def test_sys_exit_one(self) -> None:
        def _exit_one(_: argparse.Namespace) -> None:
            print("error: bad args", file=sys.stderr)
            sys.exit(1)

        success, output = run_pipeline(_exit_one, argparse.Namespace())
        assert success is False
        assert "bad args" in output

    def test_sys_exit_string(self) -> None:
        def _exit_msg(_: argparse.Namespace) -> None:
            sys.exit("fatal error message")

        success, output = run_pipeline(_exit_msg, argparse.Namespace())
        assert success is False
        assert "fatal error message" in output

    def test_unexpected_exception(self) -> None:
        def _raise(_: argparse.Namespace) -> None:
            raise RuntimeError("something broke")

        success, output = run_pipeline(_raise, argparse.Namespace())
        assert success is False
        assert "something broke" in output


# ---------------------------------------------------------------------------
# build_*_namespace
# ---------------------------------------------------------------------------

class TestBuildTempTowerNamespace:
    """Test build_temp_tower_namespace() produces correct attributes."""

    def test_basic(self) -> None:
        ns = build_temp_tower_namespace(
            filament_type="PLA",
            start_temp=230,
            end_temp=190,
            temp_step=5,
            bed_temp=60,
            fan_speed=100,
            brand_top="",
            brand_bottom="",
            nozzle_size=0.4,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/test",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.filament_type == "PLA"
        assert ns.start_temp == 230
        assert ns.end_temp == 190
        assert ns.temp_step == 5
        assert ns.bed_temp == 60
        assert ns.fan_speed == 100
        assert ns.nozzle_size == 0.4
        assert ns.printer == "COREONE"
        assert ns.ascii_gcode is False
        assert ns.output_dir == "/tmp/test"
        assert ns.no_upload is True
        assert ns.verbose is True
        assert ns.keep_files is True
        assert ns.config is None
        assert ns.bed_center is None

    def test_empty_strings_become_none(self) -> None:
        ns = build_temp_tower_namespace(
            filament_type="PLA",
            start_temp=230,
            end_temp=190,
            temp_step=5,
            bed_temp=60,
            fan_speed=100,
            brand_top="",
            brand_bottom="",
            nozzle_size=0.4,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/test",
            config_ini="",
            prusaslicer_path="",
            printer_url="",
            api_key="",
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.config_ini is None
        assert ns.prusaslicer_path is None
        assert ns.printer_url is None
        assert ns.api_key is None

    def test_sets_explicit_keys_to_block_toml_override(self) -> None:
        ns = build_temp_tower_namespace(
            filament_type="PLA",
            start_temp=230,
            end_temp=190,
            temp_step=5,
            bed_temp=60,
            fan_speed=100,
            brand_top="",
            brand_bottom="",
            nozzle_size=0.4,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/test",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert "filament_type" in ns._explicit_keys
        assert "printer" in ns._explicit_keys
        _apply_config(
            ns, {"filament_type": "ABS", "printer": "MINI"},
            explicit_keys=ns._explicit_keys,
        )
        assert ns.filament_type == "PLA"
        assert ns.printer == "COREONE"


class TestBuildFlowNamespace:
    """Test build_flow_namespace()."""

    def test_basic(self) -> None:
        ns = build_flow_namespace(
            filament_type="PETG",
            start_speed=5.0,
            end_speed=20.0,
            step=1.0,
            level_height=1.0,
            nozzle_temp=240,
            bed_temp=80,
            fan_speed=40,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/flow",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.start_speed == 5.0
        assert ns.end_speed == 20.0
        assert ns.step == 1.0
        assert ns.nozzle_temp == 240
        assert ns.layer_height == 0.2
        assert ns.extrusion_width == 0.45
        assert ns.verbose is True


class TestBuildPaNamespace:
    """Test build_pa_namespace()."""

    def test_basic(self) -> None:
        ns = build_pa_namespace(
            filament_type="PLA",
            start_pa=0.0,
            end_pa=0.10,
            pa_step=0.01,
            level_height=1.0,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/pa",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.start_pa == 0.0
        assert ns.end_pa == 0.10
        assert ns.pa_step == 0.01
        assert ns.verbose is True

    def test_method_default_tower(self) -> None:
        ns = build_pa_namespace(
            filament_type="PLA",
            start_pa=0.0,
            end_pa=0.10,
            pa_step=0.01,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/pa",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.method == "tower"
        assert ns.level_height == 1.0
        assert ns.corner_angle == 90.0
        assert ns.arm_length == 40.0
        assert ns.frame_offset == 0.0
        assert ns.wall_count == 3
        assert ns.num_layers == 4
        assert ns.frame_layers == 1
        assert ns.pattern_spacing == 1.6

    def test_method_pattern(self) -> None:
        ns = build_pa_namespace(
            filament_type="PETG",
            start_pa=0.0,
            end_pa=0.06,
            pa_step=0.01,
            method="pattern",
            level_height=2.0,
            nozzle_temp=240,
            bed_temp=80,
            fan_speed=50,
            nozzle_size=0.6,
            layer_height=0.3,
            extrusion_width=0.68,
            corner_angle=60.0,
            arm_length=20.0,
            frame_offset=5.0,
            wall_count=5,
            num_layers=8,
            frame_layers=2,
            pattern_spacing=3.0,
            printer="MK4S",
            ascii_gcode=True,
            output_dir="/tmp/pa_pattern",
            config_ini="/path/to/config.ini",
            prusaslicer_path="/usr/bin/prusa-slicer",
            printer_url="http://printer.local",
            api_key="secret123",
            no_upload=False,
            print_after_upload=True,
        )
        assert ns.method == "pattern"
        assert ns.corner_angle == 60.0
        assert ns.arm_length == 20.0
        assert ns.frame_offset == 5.0
        assert ns.wall_count == 5
        assert ns.num_layers == 8
        assert ns.frame_layers == 2
        assert ns.pattern_spacing == 3.0
        assert ns.level_height == 2.0
        assert ns.ascii_gcode is True


class TestBuildEmNamespace:
    """Test build_em_namespace()."""

    def test_basic(self) -> None:
        ns = build_em_namespace(
            filament_type="PLA",
            cube_size=40.0,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/em",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.filament_type == "PLA"
        assert ns.cube_size == 40.0
        assert ns.nozzle_temp == 215
        assert ns.bed_temp == 60
        assert ns.fan_speed == 100
        assert ns.nozzle_size == 0.4
        assert ns.layer_height == 0.2
        assert ns.extrusion_width == 0.45
        assert ns.printer == "COREONE"
        assert ns.verbose is True

    def test_empty_strings_become_none(self) -> None:
        ns = build_em_namespace(
            filament_type="PETG",
            cube_size=30.0,
            nozzle_temp=240,
            bed_temp=80,
            fan_speed=50,
            nozzle_size=0.6,
            layer_height=0.3,
            extrusion_width=0.68,
            printer="MK4S",
            ascii_gcode=True,
            output_dir="/tmp/em",
            config_ini="",
            prusaslicer_path="",
            printer_url="",
            api_key="",
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.config_ini is None
        assert ns.prusaslicer_path is None
        assert ns.printer_url is None
        assert ns.api_key is None


# ---------------------------------------------------------------------------
# find_output_file
# ---------------------------------------------------------------------------

class TestFindOutputFile:
    """Test find_output_file()."""

    def test_finds_bgcode(self, tmp_path: object) -> None:
        from pathlib import Path

        d = Path(str(tmp_path))
        (d / "tower_PLA_raw.bgcode").write_bytes(b"raw")
        (d / "tower_PLA.bgcode").write_bytes(b"final")
        result = find_output_file(str(d), ascii_gcode=False)
        assert result is not None
        assert result.name == "tower_PLA.bgcode"

    def test_finds_gcode(self, tmp_path: object) -> None:
        from pathlib import Path

        d = Path(str(tmp_path))
        (d / "flow_raw.gcode").write_bytes(b"raw")
        (d / "flow.gcode").write_bytes(b"final")
        result = find_output_file(str(d), ascii_gcode=True)
        assert result is not None
        assert result.name == "flow.gcode"

    def test_no_match(self, tmp_path: object) -> None:
        result = find_output_file(str(tmp_path), ascii_gcode=False)
        assert result is None

    def test_skips_raw(self, tmp_path: object) -> None:
        from pathlib import Path

        d = Path(str(tmp_path))
        (d / "specimen_raw.bgcode").write_bytes(b"raw")
        result = find_output_file(str(d), ascii_gcode=False)
        assert result is None

    def test_returns_most_recent_file(self, tmp_path: object) -> None:
        """When a shared output dir has files from multiple runs,
        return the most recently modified one."""
        import os
        import time
        from pathlib import Path

        d = Path(str(tmp_path))
        old_file = d / "temp_tower_PLA.bgcode"
        old_file.write_bytes(b"old")
        # Ensure different mtime by explicitly setting an older timestamp
        os.utime(old_file, (time.time() - 60, time.time() - 60))

        new_file = d / "flow_specimen_PLA.bgcode"
        new_file.write_bytes(b"new")

        result = find_output_file(str(d), ascii_gcode=False)
        assert result is not None
        assert result.name == "flow_specimen_PLA.bgcode"


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Test module-level constants are correctly populated."""

    def test_known_types_not_empty(self) -> None:
        from filament_calibrator.gui import _KNOWN_TYPES as types

        assert len(types) > 0
        assert "PLA" in types

    def test_nozzle_sizes(self) -> None:
        assert 0.4 in _NOZZLE_SIZES
        assert _NOZZLE_SIZES == sorted(_NOZZLE_SIZES)

    def test_printer_list(self) -> None:
        assert "COREONE" in _PRINTER_LIST
        assert _PRINTER_LIST == sorted(_PRINTER_LIST)


# ---------------------------------------------------------------------------
# _fresh_output_dir
# ---------------------------------------------------------------------------

class TestFreshOutputDir:
    """Test _fresh_output_dir() creates isolated directories per run."""

    def test_custom_dir_returned_as_is(self) -> None:
        assert _fresh_output_dir("/my/custom/dir") == "/my/custom/dir"

    def test_empty_string_creates_temp_dir(self) -> None:
        d1 = _fresh_output_dir("")
        d2 = _fresh_output_dir("")
        assert d1 != d2
        assert d1.startswith("/")

    def test_temp_dirs_are_unique(self) -> None:
        dirs = {_fresh_output_dir("") for _ in range(5)}
        assert len(dirs) == 5


# ---------------------------------------------------------------------------
# _clean_path
# ---------------------------------------------------------------------------


class TestCleanPath:
    """Test _clean_path() strips quotes and whitespace from pasted paths."""

    def test_no_quotes(self) -> None:
        assert _clean_path(r"C:\Users\test\config.ini") == \
            r"C:\Users\test\config.ini"

    def test_double_quotes(self) -> None:
        assert _clean_path(r'"C:\Users\test\config.ini"') == \
            r"C:\Users\test\config.ini"

    def test_single_quotes(self) -> None:
        assert _clean_path("'/home/user/config.ini'") == \
            "/home/user/config.ini"

    def test_leading_trailing_whitespace(self) -> None:
        assert _clean_path("  /path/to/file  ") == "/path/to/file"

    def test_whitespace_and_quotes(self) -> None:
        assert _clean_path('  "C:\\Users\\test\\file.ini"  ') == \
            "C:\\Users\\test\\file.ini"

    def test_empty_string(self) -> None:
        assert _clean_path("") == ""

    def test_only_quotes(self) -> None:
        assert _clean_path('""') == ""


# ---------------------------------------------------------------------------
# _is_frozen
# ---------------------------------------------------------------------------


class TestIsFrozen:
    """Test _is_frozen() detects PyInstaller bundles."""

    @patch("filament_calibrator.gui.sys")
    def test_frozen(self, mock_sys: MagicMock) -> None:
        mock_sys.frozen = True
        assert _is_frozen() is True

    def test_not_frozen(self) -> None:
        assert _is_frozen() is False


# ---------------------------------------------------------------------------
# _open_file_dialog
# ---------------------------------------------------------------------------

class TestOpenFileDialog:
    """Test _open_file_dialog() dispatches to the right backend."""

    @patch("filament_calibrator.gui.platform.system", return_value="Darwin")
    @patch("filament_calibrator.gui._osascript_file_dialog",
           return_value="/mac/file.ini")
    def test_macos_uses_osascript(self, mock_osa: MagicMock,
                                  _mock_sys: MagicMock) -> None:
        assert _open_file_dialog(title="P", filetypes=[("I", "*.ini")]) == \
            "/mac/file.ini"
        mock_osa.assert_called_once_with("P", [("I", "*.ini")])

    @patch("filament_calibrator.gui.platform.system", return_value="Linux")
    @patch("filament_calibrator.gui._tkinter_file_dialog",
           return_value="/linux/file")
    def test_linux_uses_tkinter(self, mock_tk: MagicMock,
                                _mock_sys: MagicMock) -> None:
        assert _open_file_dialog(title="Open") == "/linux/file"
        mock_tk.assert_called_once_with("Open", None)

    @patch("filament_calibrator.gui._is_frozen", return_value=True)
    @patch("filament_calibrator.gui.platform.system", return_value="Windows")
    @patch("filament_calibrator.gui._win32_file_dialog",
           return_value="C:\\file.ini")
    def test_windows_frozen_uses_win32(self, mock_w32: MagicMock,
                                       _mock_sys: MagicMock,
                                       _mock_frozen: MagicMock) -> None:
        assert _open_file_dialog(title="Pick") == "C:\\file.ini"
        mock_w32.assert_called_once_with("Pick", None)

    @patch("filament_calibrator.gui._is_frozen", return_value=False)
    @patch("filament_calibrator.gui.platform.system", return_value="Windows")
    @patch("filament_calibrator.gui._tkinter_file_dialog",
           return_value="C:\\file.ini")
    def test_windows_not_frozen_uses_tkinter(self, mock_tk: MagicMock,
                                              _mock_sys: MagicMock,
                                              _mock_frozen: MagicMock) -> None:
        assert _open_file_dialog(title="Pick") == "C:\\file.ini"
        mock_tk.assert_called_once_with("Pick", None)


# ---------------------------------------------------------------------------
# _open_directory_dialog
# ---------------------------------------------------------------------------

class TestOpenDirectoryDialog:
    """Test _open_directory_dialog() dispatches to the right backend."""

    @patch("filament_calibrator.gui.platform.system", return_value="Darwin")
    @patch("filament_calibrator.gui._osascript_directory_dialog",
           return_value="/mac/dir")
    def test_macos_uses_osascript(self, mock_osa: MagicMock,
                                  _mock_sys: MagicMock) -> None:
        assert _open_directory_dialog(title="Pick") == "/mac/dir"
        mock_osa.assert_called_once_with("Pick")

    @patch("filament_calibrator.gui.platform.system", return_value="Linux")
    @patch("filament_calibrator.gui._tkinter_directory_dialog",
           return_value="/linux/dir")
    def test_linux_uses_tkinter(self, mock_tk: MagicMock,
                                _mock_sys: MagicMock) -> None:
        assert _open_directory_dialog(title="Dir") == "/linux/dir"
        mock_tk.assert_called_once_with("Dir")

    @patch("filament_calibrator.gui._is_frozen", return_value=True)
    @patch("filament_calibrator.gui.platform.system", return_value="Windows")
    @patch("filament_calibrator.gui._win32_directory_dialog",
           return_value="C:\\outdir")
    def test_windows_frozen_uses_win32(self, mock_w32: MagicMock,
                                       _mock_sys: MagicMock,
                                       _mock_frozen: MagicMock) -> None:
        assert _open_directory_dialog(title="Dir") == "C:\\outdir"
        mock_w32.assert_called_once_with("Dir")

    @patch("filament_calibrator.gui._is_frozen", return_value=False)
    @patch("filament_calibrator.gui.platform.system", return_value="Windows")
    @patch("filament_calibrator.gui._tkinter_directory_dialog",
           return_value="C:\\outdir")
    def test_windows_not_frozen_uses_tkinter(self, mock_tk: MagicMock,
                                              _mock_sys: MagicMock,
                                              _mock_frozen: MagicMock) -> None:
        assert _open_directory_dialog(title="Dir") == "C:\\outdir"
        mock_tk.assert_called_once_with("Dir")


# ---------------------------------------------------------------------------
# _run_osascript
# ---------------------------------------------------------------------------

class TestRunOsascript:
    """Test _run_osascript() helper."""

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_path(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="/selected/path\n")
        assert _run_osascript("choose file") == "/selected/path"
        mock_run.assert_called_once_with(
            ["osascript", "-e", "choose file"],
            capture_output=True, text=True, timeout=120,
        )

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_cancel(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="")
        assert _run_osascript("choose file") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=120)
        assert _run_osascript("choose file") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_os_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError()
        assert _run_osascript("choose file") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_file_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError()
        assert _run_osascript("choose file") is None


# ---------------------------------------------------------------------------
# _osascript_file_dialog
# ---------------------------------------------------------------------------

class TestOsascriptFileDialog:
    """Test _osascript_file_dialog() AppleScript generation."""

    @patch("filament_calibrator.gui._run_osascript",
           return_value="/path/f.ini")
    def test_with_filetypes(self, mock_osa: MagicMock) -> None:
        result = _osascript_file_dialog("Pick", [("INI", "*.ini")])
        assert result == "/path/f.ini"
        script = mock_osa.call_args[0][0]
        assert '"ini"' in script
        assert "choose file" in script

    @patch("filament_calibrator.gui._run_osascript",
           return_value="/path/f")
    def test_without_filetypes(self, mock_osa: MagicMock) -> None:
        _osascript_file_dialog("Open")
        script = mock_osa.call_args[0][0]
        assert "of type" not in script

    @patch("filament_calibrator.gui._run_osascript",
           return_value="/path/f")
    def test_filetypes_none(self, mock_osa: MagicMock) -> None:
        _osascript_file_dialog("Open", None)
        script = mock_osa.call_args[0][0]
        assert "of type" not in script

    @patch("filament_calibrator.gui._run_osascript",
           return_value="/path/f")
    def test_star_wildcard_skipped(self, mock_osa: MagicMock) -> None:
        _osascript_file_dialog("Open", [("All", "*.*")])
        script = mock_osa.call_args[0][0]
        # '*' is not a valid UTI, should not appear in of type clause
        assert "of type" not in script


# ---------------------------------------------------------------------------
# _osascript_directory_dialog
# ---------------------------------------------------------------------------

class TestOsascriptDirectoryDialog:
    """Test _osascript_directory_dialog() AppleScript generation."""

    @patch("filament_calibrator.gui._run_osascript",
           return_value="/path/dir")
    def test_calls_choose_folder(self, mock_osa: MagicMock) -> None:
        assert _osascript_directory_dialog("Pick") == "/path/dir"
        script = mock_osa.call_args[0][0]
        assert "choose folder" in script
        assert "Pick" in script


# ---------------------------------------------------------------------------
# _tkinter_file_dialog
# ---------------------------------------------------------------------------

class TestTkinterFileDialog:
    """Test _tkinter_file_dialog() subprocess-based file picker."""

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_selected_path(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="/path/to/config.ini\n")
        result = _tkinter_file_dialog(title="Pick",
                                      filetypes=[("INI", "*.ini")])
        assert result == "/path/to/config.ini"
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][0] == sys.executable

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_cancel(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="\n")
        assert _tkinter_file_dialog("Pick") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="")
        assert _tkinter_file_dialog("Pick") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=120)
        assert _tkinter_file_dialog("Pick") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_os_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError("no python")
        assert _tkinter_file_dialog("Pick") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_file_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError()
        assert _tkinter_file_dialog("Pick") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_no_filetypes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="/some/file\n")
        assert _tkinter_file_dialog(title="Open") == "/some/file"

    @patch("filament_calibrator.gui.subprocess.run")
    def test_filetypes_in_script(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="/x.ini\n")
        _tkinter_file_dialog("Pick", filetypes=[("INI files", "*.ini")])
        script = mock_run.call_args[0][0][2]
        assert "*.ini" in script


# ---------------------------------------------------------------------------
# _tkinter_directory_dialog
# ---------------------------------------------------------------------------

class TestTkinterDirectoryDialog:
    """Test _tkinter_directory_dialog() subprocess-based directory picker."""

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_selected_path(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="/path/to/output\n")
        assert _tkinter_directory_dialog(title="Pick dir") == "/path/to/output"

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_cancel(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="")
        assert _tkinter_directory_dialog("Pick") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=120)
        assert _tkinter_directory_dialog("Pick") is None

    @patch("filament_calibrator.gui.subprocess.run")
    def test_returns_none_on_os_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError()
        assert _tkinter_directory_dialog("Pick") is None


# ---------------------------------------------------------------------------
# _win32_file_dialog
# ---------------------------------------------------------------------------


class TestWin32FileDialog:
    """Test _win32_file_dialog() Win32 native file picker."""

    def test_returns_none_on_no_windll(self) -> None:
        """Non-Windows platforms raise AttributeError on ctypes.windll."""
        result = _win32_file_dialog("Pick", [("INI", "*.ini")])
        assert result is None

    def test_returns_none_without_filetypes(self) -> None:
        result = _win32_file_dialog("Pick")
        assert result is None

    def test_returns_path_when_user_selects(self) -> None:
        """Mock ctypes.windll to simulate a successful file selection."""
        import ctypes

        mock_windll = MagicMock()
        mock_windll.comdlg32.GetOpenFileNameW.return_value = True
        with patch.object(ctypes, "windll", mock_windll, create=True):
            result = _win32_file_dialog(
                "Pick", filetypes=[("INI", "*.ini")],
            )
        # ctypes.create_unicode_buffer starts empty, so buf.value is ""
        assert result is None  # empty buffer → None

    def test_returns_none_when_user_cancels(self) -> None:
        """Mock ctypes.windll to simulate cancel."""
        import ctypes

        mock_windll = MagicMock()
        mock_windll.comdlg32.GetOpenFileNameW.return_value = False
        with patch.object(ctypes, "windll", mock_windll, create=True):
            result = _win32_file_dialog("Pick")
        assert result is None

    def test_no_filetypes_filter(self) -> None:
        """Calling without filetypes should still work."""
        import ctypes

        mock_windll = MagicMock()
        mock_windll.comdlg32.GetOpenFileNameW.return_value = False
        with patch.object(ctypes, "windll", mock_windll, create=True):
            result = _win32_file_dialog("Pick", filetypes=None)
        assert result is None

    def test_exception_returns_none(self) -> None:
        """Any exception inside the function returns None."""
        import ctypes

        mock_windll = MagicMock()
        mock_windll.comdlg32.GetOpenFileNameW.side_effect = OSError("fail")
        with patch.object(ctypes, "windll", mock_windll, create=True):
            result = _win32_file_dialog("Pick")
        assert result is None


# ---------------------------------------------------------------------------
# _win32_directory_dialog
# ---------------------------------------------------------------------------


class TestWin32DirectoryDialog:
    """Test _win32_directory_dialog() Win32 native directory picker."""

    def test_returns_none_on_no_windll(self) -> None:
        """Non-Windows platforms raise AttributeError on ctypes.windll."""
        result = _win32_directory_dialog("Pick")
        assert result is None

    def test_returns_none_when_user_cancels(self) -> None:
        """Mock ctypes.windll to simulate cancel."""
        import ctypes

        mock_windll = MagicMock()
        mock_windll.shell32.SHBrowseForFolderW.return_value = None
        with patch.object(ctypes, "windll", mock_windll, create=True):
            result = _win32_directory_dialog("Pick")
        assert result is None

    def test_returns_none_on_empty_path(self) -> None:
        """Mock ctypes.windll to simulate selection with empty path."""
        import ctypes

        mock_windll = MagicMock()
        mock_windll.shell32.SHBrowseForFolderW.return_value = 12345
        with patch.object(ctypes, "windll", mock_windll, create=True):
            result = _win32_directory_dialog("Pick")
        # SHGetPathFromIDListW is called but buffer is empty
        assert result is None

    def test_exception_returns_none(self) -> None:
        """Any exception inside the function returns None."""
        import ctypes

        mock_windll = MagicMock()
        mock_windll.shell32.SHBrowseForFolderW.side_effect = OSError("fail")
        with patch.object(ctypes, "windll", mock_windll, create=True):
            result = _win32_directory_dialog("Pick")
        assert result is None


# ---------------------------------------------------------------------------
# snap_nozzle_size
# ---------------------------------------------------------------------------

class TestSnapNozzleSize:
    """Test snap_nozzle_size() nearest-match logic."""

    def test_exact_match(self) -> None:
        assert snap_nozzle_size(0.4) == 0.4

    def test_exact_match_0_6(self) -> None:
        assert snap_nozzle_size(0.6) == 0.6

    def test_between_snaps_to_nearest(self) -> None:
        # 0.35 is between 0.3 and 0.4 → 0.35 is equidistant, picks 0.3
        # (min picks the first match with equal distance)
        result = snap_nozzle_size(0.35)
        assert result in (0.3, 0.4)

    def test_below_minimum(self) -> None:
        assert snap_nozzle_size(0.1) == 0.25

    def test_above_maximum(self) -> None:
        assert snap_nozzle_size(1.0) == 0.8

    def test_close_to_0_5(self) -> None:
        assert snap_nozzle_size(0.48) == 0.5


# ---------------------------------------------------------------------------
# apply_ini_to_session
# ---------------------------------------------------------------------------

class TestApplyIniToSession:
    """Test apply_ini_to_session() session-state population."""

    def test_full_dict(self) -> None:
        state: dict = {}
        ini_vals = {
            "nozzle_temp": 220,
            "bed_temp": 65,
            "fan_speed": 80,
            "layer_height": 0.15,
            "extrusion_width": 0.45,
            "nozzle_diameter": 0.4,
            "printer_model": "COREONE",
            "bed_center": "125,110",
            "nozzle_high_flow": True,
            "nozzle_hardened": True,
        }
        apply_ini_to_session(state, ini_vals)

        # Nozzle temp → EM + flow + PA + retraction + shrinkage tabs, temp tower range.
        assert state["em_nozzle_temp"] == 220
        assert state["flow_nozzle_temp"] == 220
        assert state["pa_nozzle_temp"] == 220
        assert state["retraction_nozzle_temp"] == 220
        assert state["shrinkage_nozzle_temp"] == 220
        assert state["tt_start_temp"] == 235
        assert state["tt_end_temp"] == 205

        # Bed temp → all six tabs.
        assert state["tt_bed_temp"] == 65
        assert state["em_bed_temp"] == 65
        assert state["flow_bed_temp"] == 65
        assert state["pa_bed_temp"] == 65
        assert state["retraction_bed_temp"] == 65
        assert state["shrinkage_bed_temp"] == 65

        # Fan speed → all six tabs.
        assert state["tt_fan"] == 80
        assert state["em_fan"] == 80
        assert state["flow_fan"] == 80
        assert state["pa_fan"] == 80
        assert state["retraction_fan"] == 80
        assert state["shrinkage_fan"] == 80

        # Layer height / extrusion width → EM + flow + PA + retraction + shrinkage.
        assert state["em_lh"] == 0.15
        assert state["flow_lh"] == 0.15
        assert state["pa_lh"] == 0.15
        assert state["retraction_lh"] == 0.15
        assert state["shrinkage_lh"] == 0.15
        assert state["em_ew"] == 0.45
        assert state["flow_ew"] == 0.45
        assert state["pa_ew"] == 0.45
        assert state["retraction_ew"] == 0.45
        assert state["shrinkage_ew"] == 0.45

        # Selectbox widget keys (written directly for Streamlit key= binding).
        assert state["sidebar_nozzle_size"] == 0.4
        assert state["sidebar_printer"] == "COREONE"

        # Nozzle flags → sidebar checkboxes.
        assert state["sidebar_nozzle_high_flow"] is True
        assert state["sidebar_nozzle_hardened"] is True

    def test_partial_dict_only_temp(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {"nozzle_temp": 210})
        assert state["em_nozzle_temp"] == 210
        assert state["flow_nozzle_temp"] == 210
        assert state["pa_nozzle_temp"] == 210
        assert state["retraction_nozzle_temp"] == 210
        assert state["shrinkage_nozzle_temp"] == 210
        assert state["tt_start_temp"] == 225
        assert state["tt_end_temp"] == 195
        assert "tt_bed_temp" not in state
        assert "flow_lh" not in state

    def test_empty_dict(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {})
        assert state == {}

    def test_nozzle_diameter_snapped(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {"nozzle_diameter": 0.42})
        assert state["sidebar_nozzle_size"] == 0.4

    def test_unknown_printer_not_stored(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {"printer_model": "UNKNOWNXYZ"})
        assert "sidebar_printer" not in state

    def test_known_printer_uppercased(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {"printer_model": "coreone"})
        assert state["sidebar_printer"] == "COREONE"

    def test_bed_center_ignored(self) -> None:
        """bed_center from INI is not stored — pipelines compute it from printer."""
        state: dict = {}
        apply_ini_to_session(state, {"bed_center": "100,100"})
        assert "_ini_bed_center" not in state

    def test_known_filament_type_stored(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {"filament_type": "petg"})
        assert state["sidebar_filament_type"] == "PETG"

    def test_unknown_filament_type_stored(self) -> None:
        """Custom types (e.g. POM, FLEX) are stored so the selectbox shows them."""
        state: dict = {}
        apply_ini_to_session(state, {"filament_type": "POM"})
        assert state["sidebar_filament_type"] == "POM"

    def test_nozzle_flags_set(self) -> None:
        state: dict = {}
        apply_ini_to_session(
            state,
            {"nozzle_high_flow": True, "nozzle_hardened": False},
        )
        assert state["sidebar_nozzle_high_flow"] is True
        assert state["sidebar_nozzle_hardened"] is False

    def test_nozzle_flags_missing(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {"nozzle_temp": 210})
        assert "sidebar_nozzle_high_flow" not in state
        assert "sidebar_nozzle_hardened" not in state

    def test_sidebar_false_skips_sidebar_keys(self) -> None:
        """sidebar=False skips sidebar widget keys (post-render re-apply)."""
        state: dict = {}
        ini_vals = {
            "nozzle_temp": 230,
            "bed_temp": 70,
            "nozzle_diameter": 0.6,
            "printer_model": "COREONE",
            "filament_type": "PETG",
            "nozzle_high_flow": True,
            "nozzle_hardened": True,
        }
        apply_ini_to_session(state, ini_vals, sidebar=False)
        # Tab keys are written.
        assert state["em_nozzle_temp"] == 230
        assert state["tt_start_temp"] == 245
        assert state["tt_end_temp"] == 215
        assert state["pa_bed_temp"] == 70
        # Sidebar keys are NOT written.
        assert "sidebar_nozzle_size" not in state
        assert "sidebar_printer" not in state
        assert "sidebar_filament_type" not in state
        assert "sidebar_nozzle_high_flow" not in state
        assert "sidebar_nozzle_hardened" not in state


# ---------------------------------------------------------------------------
# apply_toml_to_session
# ---------------------------------------------------------------------------

class TestApplyTomlToSession:
    """Test apply_toml_to_session() TOML config population."""

    def test_full_config(self) -> None:
        state: dict = {}
        cfg = {
            "printer_url": "http://192.168.1.100",
            "api_key": "secret123",
            "config_ini": "/path/to/config.ini",
            "prusaslicer_path": "/usr/bin/prusa-slicer",
            "output_dir": "/tmp/output",
            "filament_type": "ABS",
            "nozzle_size": 0.6,
            "printer": "COREONE",
        }
        apply_toml_to_session(state, cfg)

        assert state["printer_url"] == "http://192.168.1.100"
        assert state["api_key"] == "secret123"
        assert state["config_ini"] == "/path/to/config.ini"
        assert state["prusaslicer_path"] == "/usr/bin/prusa-slicer"
        assert state["output_dir"] == "/tmp/output"
        assert state["_toml_filament_type"] == "ABS"
        assert state["_toml_nozzle_size"] == 0.6
        assert state["_toml_printer"] == "COREONE"

    def test_partial_config(self) -> None:
        state: dict = {}
        apply_toml_to_session(state, {"printer_url": "http://10.0.0.1"})
        assert state["printer_url"] == "http://10.0.0.1"
        assert "api_key" not in state
        assert "_toml_filament_type" not in state

    def test_empty_config(self) -> None:
        state: dict = {}
        apply_toml_to_session(state, {})
        assert state == {}

    def test_does_not_overwrite_existing(self) -> None:
        state = {"printer_url": "http://existing"}
        apply_toml_to_session(state, {"printer_url": "http://new"})
        assert state["printer_url"] == "http://existing"

    def test_nozzle_size_snapped(self) -> None:
        state: dict = {}
        apply_toml_to_session(state, {"nozzle_size": 0.42})
        assert state["_toml_nozzle_size"] == 0.4

    def test_unknown_filament_type_not_stored(self) -> None:
        state: dict = {}
        apply_toml_to_session(state, {"filament_type": "EXOTIC123"})
        assert "_toml_filament_type" not in state

    def test_unknown_printer_not_stored(self) -> None:
        state: dict = {}
        apply_toml_to_session(state, {"printer": "UNKNOWNXYZ"})
        assert "_toml_printer" not in state

    def test_nozzle_size_int(self) -> None:
        state: dict = {}
        apply_toml_to_session(state, {"nozzle_size": 1})
        assert state["_toml_nozzle_size"] == 0.8

    def test_nozzle_size_string_ignored(self) -> None:
        state: dict = {}
        apply_toml_to_session(state, {"nozzle_size": "bad"})
        assert "_toml_nozzle_size" not in state

    def test_toml_keys_not_overwritten_once_set(self) -> None:
        state = {"_toml_filament_type": "PLA"}
        apply_toml_to_session(state, {"filament_type": "ABS"})
        assert state["_toml_filament_type"] == "PLA"

    def test_nozzle_flags_set(self) -> None:
        state: dict = {}
        apply_toml_to_session(
            state, {"nozzle_high_flow": True, "nozzle_hardened": True}
        )
        assert state["_toml_nozzle_high_flow"] is True
        assert state["_toml_nozzle_hardened"] is True

    def test_nozzle_flags_not_overwritten(self) -> None:
        state = {
            "_toml_nozzle_high_flow": False,
            "_toml_nozzle_hardened": False,
        }
        apply_toml_to_session(
            state, {"nozzle_high_flow": True, "nozzle_hardened": True}
        )
        assert state["_toml_nozzle_high_flow"] is False
        assert state["_toml_nozzle_hardened"] is False


# ---------------------------------------------------------------------------
# upload_to_printer
# ---------------------------------------------------------------------------

class TestUploadToPrinter:
    """Test upload_to_printer() PrusaLink upload wrapper."""

    @patch("filament_calibrator.gui.gl.prusalink_upload",
           return_value="tower_PLA.bgcode")
    def test_success(self, mock_upload: MagicMock) -> None:
        ok, msg = upload_to_printer(
            printer_url="http://10.0.0.1",
            api_key="key123",
            gcode_path="/tmp/tower_PLA.bgcode",
        )
        assert ok is True
        assert "tower_PLA.bgcode" in msg
        assert "Print started" not in msg
        mock_upload.assert_called_once_with(
            base_url="http://10.0.0.1",
            api_key="key123",
            gcode_path="/tmp/tower_PLA.bgcode",
            print_after_upload=False,
        )

    @patch("filament_calibrator.gui.gl.prusalink_upload",
           return_value="flow_PLA.bgcode")
    def test_success_with_print(self, mock_upload: MagicMock) -> None:
        ok, msg = upload_to_printer(
            printer_url="http://10.0.0.1",
            api_key="key123",
            gcode_path="/tmp/flow_PLA.bgcode",
            print_after_upload=True,
        )
        assert ok is True
        assert "flow_PLA.bgcode" in msg
        assert "Print started" in msg
        mock_upload.assert_called_once_with(
            base_url="http://10.0.0.1",
            api_key="key123",
            gcode_path="/tmp/flow_PLA.bgcode",
            print_after_upload=True,
        )

    @patch("filament_calibrator.gui.gl.prusalink_upload",
           side_effect=ConnectionError("Connection refused"))
    def test_failure(self, mock_upload: MagicMock) -> None:
        ok, msg = upload_to_printer(
            printer_url="http://10.0.0.1",
            api_key="key123",
            gcode_path="/tmp/tower.bgcode",
        )
        assert ok is False
        assert "Upload failed" in msg
        assert "Connection refused" in msg


# ---------------------------------------------------------------------------
# build_calibration_results
# ---------------------------------------------------------------------------

class TestBuildCalibrationResults:
    """Test build_calibration_results() helper."""

    def test_all_set(self) -> None:
        r = build_calibration_results(
            set_temp=True, temperature=215,
            set_flow=True, max_volumetric_speed=12.5,
            set_pa=True, pa_value=0.04,
            set_em=True, extrusion_multiplier=0.95,
            set_retraction=True, retraction_length=0.6,
            set_retraction_speed=True, retraction_speed=40.0,
            set_shrinkage=True, xy_shrinkage=0.5, z_shrinkage=0.3,
            printer="COREONE",
        )
        assert r.temperature == 215
        assert r.max_volumetric_speed == 12.5
        assert r.pa_value == 0.04
        assert r.extrusion_multiplier == 0.95
        assert r.retraction_length == 0.6
        assert r.retraction_speed == 40.0
        assert r.xy_shrinkage == 0.5
        assert r.z_shrinkage == 0.3
        assert r.printer == "COREONE"

    def test_none_set(self) -> None:
        r = build_calibration_results(
            set_temp=False, temperature=215,
            set_flow=False, max_volumetric_speed=12.5,
            set_pa=False, pa_value=0.04,
            set_em=False, extrusion_multiplier=0.95,
            set_retraction=False, retraction_length=0.8,
            set_retraction_speed=False, retraction_speed=30.0,
            set_shrinkage=False, xy_shrinkage=0.5, z_shrinkage=0.3,
            printer="COREONE",
        )
        assert r.temperature is None
        assert r.max_volumetric_speed is None
        assert r.pa_value is None
        assert r.extrusion_multiplier is None
        assert r.retraction_length is None
        assert r.retraction_speed is None
        assert r.xy_shrinkage is None
        assert r.z_shrinkage is None
        assert r.printer == "COREONE"

    def test_partial_temp_only(self) -> None:
        r = build_calibration_results(
            set_temp=True, temperature=230,
            set_flow=False, max_volumetric_speed=11.0,
            set_pa=False, pa_value=0.04,
            set_em=False, extrusion_multiplier=1.0,
            set_retraction=False, retraction_length=0.8,
            set_retraction_speed=False, retraction_speed=30.0,
            set_shrinkage=False, xy_shrinkage=0.0, z_shrinkage=0.0,
            printer="MINI",
        )
        assert r.temperature == 230
        assert r.max_volumetric_speed is None
        assert r.pa_value is None
        assert r.extrusion_multiplier is None
        assert r.retraction_length is None
        assert r.xy_shrinkage is None
        assert r.z_shrinkage is None
        assert r.printer == "MINI"

    def test_partial_em_only(self) -> None:
        r = build_calibration_results(
            set_temp=False, temperature=215,
            set_flow=False, max_volumetric_speed=11.0,
            set_pa=False, pa_value=0.04,
            set_em=True, extrusion_multiplier=0.97,
            set_retraction=False, retraction_length=0.8,
            set_retraction_speed=False, retraction_speed=30.0,
            set_shrinkage=False, xy_shrinkage=0.0, z_shrinkage=0.0,
            printer="COREONE",
        )
        assert r.temperature is None
        assert r.extrusion_multiplier == 0.97
        assert r.retraction_length is None
        assert r.xy_shrinkage is None

    def test_partial_retraction_only(self) -> None:
        r = build_calibration_results(
            set_temp=False, temperature=215,
            set_flow=False, max_volumetric_speed=11.0,
            set_pa=False, pa_value=0.04,
            set_em=False, extrusion_multiplier=1.0,
            set_retraction=True, retraction_length=0.6,
            set_retraction_speed=False, retraction_speed=30.0,
            set_shrinkage=False, xy_shrinkage=0.0, z_shrinkage=0.0,
            printer="COREONE",
        )
        assert r.temperature is None
        assert r.retraction_length == 0.6
        assert r.retraction_speed is None
        assert r.xy_shrinkage is None

    def test_partial_shrinkage_only(self) -> None:
        r = build_calibration_results(
            set_temp=False, temperature=215,
            set_flow=False, max_volumetric_speed=11.0,
            set_pa=False, pa_value=0.04,
            set_em=False, extrusion_multiplier=1.0,
            set_retraction=False, retraction_length=0.8,
            set_retraction_speed=False, retraction_speed=30.0,
            set_shrinkage=True, xy_shrinkage=0.5, z_shrinkage=0.3,
            printer="COREONE",
        )
        assert r.temperature is None
        assert r.retraction_length is None
        assert r.xy_shrinkage == 0.5
        assert r.z_shrinkage == 0.3


# ---------------------------------------------------------------------------
# build_retraction_namespace
# ---------------------------------------------------------------------------

class TestBuildRetractionNamespace:
    """Test build_retraction_namespace()."""

    def test_basic(self) -> None:
        ns = build_retraction_namespace(
            filament_type="PLA",
            start_retraction=0.0,
            end_retraction=2.0,
            retraction_step=0.1,
            level_height=1.0,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/retraction",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.start_retraction == 0.0
        assert ns.end_retraction == 2.0
        assert ns.retraction_step == 0.1
        assert ns.level_height == 1.0
        assert ns.nozzle_temp == 215
        assert ns.layer_height == 0.2
        assert ns.extrusion_width == 0.45
        assert ns.verbose is True
        assert ns.keep_files is True

    def test_empty_strings_become_none(self) -> None:
        ns = build_retraction_namespace(
            filament_type="PETG",
            start_retraction=0.0,
            end_retraction=2.0,
            retraction_step=0.1,
            nozzle_temp=240,
            bed_temp=80,
            fan_speed=50,
            nozzle_size=0.6,
            layer_height=0.3,
            extrusion_width=0.68,
            printer="MK4S",
            ascii_gcode=True,
            output_dir="/tmp/retraction",
            config_ini="",
            prusaslicer_path="",
            printer_url="",
            api_key="",
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.config_ini is None
        assert ns.prusaslicer_path is None
        assert ns.printer_url is None
        assert ns.api_key is None


# ---------------------------------------------------------------------------
# build_shrinkage_namespace
# ---------------------------------------------------------------------------


class TestBuildShrinkageNamespace:
    """Test build_shrinkage_namespace()."""

    def test_basic(self) -> None:
        ns = build_shrinkage_namespace(
            filament_type="PLA",
            arm_length=100.0,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/shrinkage",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.arm_length == 100.0
        assert ns.nozzle_temp == 215
        assert ns.layer_height == 0.2
        assert ns.extrusion_width == 0.45
        assert ns.verbose is True
        assert ns.keep_files is True

    def test_empty_strings_become_none(self) -> None:
        ns = build_shrinkage_namespace(
            filament_type="PETG",
            arm_length=80.0,
            nozzle_temp=240,
            bed_temp=80,
            fan_speed=50,
            nozzle_size=0.6,
            layer_height=0.3,
            extrusion_width=0.68,
            printer="MK4S",
            ascii_gcode=True,
            output_dir="/tmp/shrinkage",
            config_ini="",
            prusaslicer_path="",
            printer_url="",
            api_key="",
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.config_ini is None
        assert ns.prusaslicer_path is None
        assert ns.printer_url is None
        assert ns.api_key is None


# ---------------------------------------------------------------------------
# build_retraction_speed_namespace
# ---------------------------------------------------------------------------


class TestBuildRetractionSpeedNamespace:
    """Test build_retraction_speed_namespace()."""

    def test_basic(self) -> None:
        ns = build_retraction_speed_namespace(
            filament_type="PLA",
            retraction_length=0.8,
            start_speed=20.0,
            end_speed=60.0,
            speed_step=5.0,
            level_height=1.0,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/retspeed",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.retraction_length == 0.8
        assert ns.start_speed == 20.0
        assert ns.end_speed == 60.0
        assert ns.speed_step == 5.0
        assert ns.verbose is True
        assert ns.keep_files is True


# ---------------------------------------------------------------------------
# build_bridge_namespace
# ---------------------------------------------------------------------------


class TestBuildBridgeNamespace:
    """Test build_bridge_namespace()."""

    def test_basic(self) -> None:
        ns = build_bridge_namespace(
            filament_type="PLA",
            spans="10,20,30",
            pillar_height=15.0,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/bridge",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.spans == "10,20,30"
        assert ns.pillar_height == 15.0
        assert ns.verbose is True
        assert ns.keep_files is True


# ---------------------------------------------------------------------------
# build_overhang_namespace
# ---------------------------------------------------------------------------


class TestBuildOverhangNamespace:
    """Test build_overhang_namespace()."""

    def test_basic(self) -> None:
        ns = build_overhang_namespace(
            filament_type="PLA",
            angles="20,30,40,50",
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/overhang",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.angles == "20,30,40,50"
        assert ns.verbose is True
        assert ns.keep_files is True


# ---------------------------------------------------------------------------
# build_tolerance_namespace
# ---------------------------------------------------------------------------


class TestBuildToleranceNamespace:
    """Test build_tolerance_namespace()."""

    def test_basic(self) -> None:
        ns = build_tolerance_namespace(
            filament_type="PLA",
            diameters="3,5,8,10",
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/tol",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.diameters == "3,5,8,10"
        assert ns.verbose is True
        assert ns.keep_files is True


# ---------------------------------------------------------------------------
# build_cooling_namespace
# ---------------------------------------------------------------------------


class TestBuildCoolingNamespace:
    """Test build_cooling_namespace()."""

    def test_basic(self) -> None:
        ns = build_cooling_namespace(
            filament_type="PLA",
            start_fan=0,
            end_fan=100,
            fan_step=10,
            level_height=1.0,
            nozzle_temp=215,
            bed_temp=60,
            fan_speed=100,
            nozzle_size=0.4,
            layer_height=0.2,
            extrusion_width=0.45,
            printer="COREONE",
            ascii_gcode=False,
            output_dir="/tmp/cool",
            config_ini=None,
            prusaslicer_path=None,
            printer_url=None,
            api_key=None,
            no_upload=True,
            print_after_upload=False,
        )
        assert ns.start_fan == 0
        assert ns.end_fan == 100
        assert ns.fan_step == 10
        assert ns.level_height == 1.0
        assert ns.verbose is True
        assert ns.keep_files is True


# ---------------------------------------------------------------------------
# _check_printer_temps
# ---------------------------------------------------------------------------


class TestCheckPrinterTemps:
    def test_returns_none_when_within_limits(self):
        with patch.dict(gl.PRINTER_PRESETS, {
            "COREONE": {"max_nozzle_temp": 290, "max_bed_temp": 120},
        }):
            assert _check_printer_temps("COREONE", 250, 60) is None

    def test_nozzle_temp_exceeds(self):
        with patch.dict(gl.PRINTER_PRESETS, {
            "COREONE": {"max_nozzle_temp": 290, "max_bed_temp": 120},
        }):
            result = _check_printer_temps("COREONE", 300, 60)
            assert result is not None
            assert "300" in result
            assert "290" in result

    def test_bed_temp_exceeds(self):
        with patch.dict(gl.PRINTER_PRESETS, {
            "COREONE": {"max_nozzle_temp": 290, "max_bed_temp": 120},
        }):
            result = _check_printer_temps("COREONE", 200, 130)
            assert result is not None
            assert "130" in result
            assert "120" in result

    def test_unknown_printer_returns_none(self):
        with patch("gcode_lib.resolve_printer", side_effect=ValueError("nope")):
            assert _check_printer_temps("NOPE", 999, 999) is None

    def test_missing_max_keys_returns_none(self):
        with patch.dict(gl.PRINTER_PRESETS, {
            "COREONE": {},
        }):
            assert _check_printer_temps("COREONE", 999, 999) is None

    def test_printer_not_in_presets_returns_none(self):
        with patch("gcode_lib.resolve_printer", return_value="NEWPRINTER"), \
             patch.dict(gl.PRINTER_PRESETS, {}, clear=True):
            assert _check_printer_temps("NEWPRINTER", 999, 999) is None


# ---------------------------------------------------------------------------
# _results_key
# ---------------------------------------------------------------------------


class TestResultsKey:
    """Test _results_key() composite key builder."""

    def test_basic(self) -> None:
        assert _results_key("PCTG", 0.4, "COREONE") == "PCTG|0.4|COREONE"

    def test_case_normalization(self) -> None:
        assert _results_key("pctg", 0.4, "coreone") == "PCTG|0.4|COREONE"

    def test_different_nozzle(self) -> None:
        assert _results_key("PLA", 0.6, "MK4S") == "PLA|0.6|MK4S"


# ---------------------------------------------------------------------------
# results_to_dict
# ---------------------------------------------------------------------------


class TestResultsToDict:
    """Test results_to_dict() serialization."""

    def test_all_fields(self) -> None:
        d = results_to_dict(
            set_temp=True, temperature=215,
            set_em=True, extrusion_multiplier=0.95,
            set_retraction=True, retraction_length=0.6,
            set_retraction_speed=True, retraction_speed=40.0,
            set_pa=True, pa_value=0.04,
            set_flow=True, max_volumetric_speed=12.5,
            set_shrinkage=True, xy_shrinkage=0.5, z_shrinkage=0.3,
        )
        assert d["set_temp"] is True
        assert d["temperature"] == 215
        assert d["set_em"] is True
        assert d["extrusion_multiplier"] == 0.95
        assert d["set_retraction"] is True
        assert d["retraction_length"] == 0.6
        assert d["set_retraction_speed"] is True
        assert d["retraction_speed"] == 40.0
        assert d["set_pa"] is True
        assert d["pa_value"] == 0.04
        assert d["set_flow"] is True
        assert d["max_volumetric_speed"] == 12.5
        assert d["set_shrinkage"] is True
        assert d["xy_shrinkage"] == 0.5
        assert d["z_shrinkage"] == 0.3

    def test_all_disabled(self) -> None:
        d = results_to_dict(
            set_temp=False, temperature=200,
            set_em=False, extrusion_multiplier=1.0,
            set_retraction=False, retraction_length=0.8,
            set_retraction_speed=False, retraction_speed=30.0,
            set_pa=False, pa_value=0.04,
            set_flow=False, max_volumetric_speed=11.0,
            set_shrinkage=False, xy_shrinkage=0.0, z_shrinkage=0.0,
        )
        assert d["set_temp"] is False
        assert d["set_shrinkage"] is False
        assert d["set_retraction_speed"] is False
        # Values are still serialized (booleans gate usage at restore time).
        assert d["temperature"] == 200
        assert d["xy_shrinkage"] == 0.0
        assert d["retraction_speed"] == 30.0


# ---------------------------------------------------------------------------
# apply_saved_results_to_session
# ---------------------------------------------------------------------------


class TestApplySavedResultsToSession:
    """Test apply_saved_results_to_session() state update."""

    def test_full_restore(self) -> None:
        state: dict = {}
        saved = {
            "set_temp": True, "temperature": 230,
            "set_em": True, "extrusion_multiplier": 0.93,
            "set_retraction": True, "retraction_length": 0.6,
            "set_retraction_speed": True, "retraction_speed": 40.0,
            "set_pa": True, "pa_value": 0.05,
            "set_flow": True, "max_volumetric_speed": 14.0,
            "set_shrinkage": True, "xy_shrinkage": 0.5, "z_shrinkage": 0.3,
        }
        apply_saved_results_to_session(state, saved)
        assert state["res_set_temp"] is True
        assert state["res_temp"] == 230
        assert state["res_set_em"] is True
        assert state["res_set_retraction_speed"] is True
        assert state["res_retraction_speed"] == 40.0
        assert state["res_em"] == 0.93
        assert state["res_set_retraction"] is True
        assert state["res_retraction"] == 0.6
        assert state["res_set_pa"] is True
        assert state["res_pa"] == 0.05
        assert state["res_set_flow"] is True
        assert state["res_flow"] == 14.0
        assert state["res_set_shrinkage"] is True
        assert state["res_xy_shrinkage"] == 0.5
        assert state["res_z_shrinkage"] == 0.3

    def test_partial_restore(self) -> None:
        state: dict = {}
        saved = {"set_temp": True, "temperature": 220}
        apply_saved_results_to_session(state, saved)
        assert state["res_set_temp"] is True
        assert state["res_temp"] == 220
        # Other keys not set.
        assert "res_set_em" not in state
        assert "res_set_shrinkage" not in state

    def test_empty_dict(self) -> None:
        state: dict = {}
        apply_saved_results_to_session(state, {})
        assert len(state) == 0

    def test_mapping_coverage(self) -> None:
        """Every _RESULTS_STATE_MAPPING key is exercised."""
        saved = {k: 42 for k in _RESULTS_STATE_MAPPING}
        state: dict = {}
        apply_saved_results_to_session(state, saved)
        for json_key, state_key in _RESULTS_STATE_MAPPING.items():
            assert state[state_key] == 42


# ---------------------------------------------------------------------------
# load_saved_results / save_results
# ---------------------------------------------------------------------------


class TestLoadSaveResults:
    """Test load_saved_results() and save_results() persistence."""

    def test_round_trip(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "results.json"
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            values = {"set_temp": True, "temperature": 230}
            save_results("PCTG", 0.4, "COREONE", values)
            loaded = load_saved_results("PCTG", 0.4, "COREONE")
            assert loaded == values

    def test_missing_file(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent" / "results.json"
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            assert load_saved_results("PLA", 0.4, "MK4S") is None

    def test_corrupt_json(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "results.json"
        fake_path.write_text("not valid json {{{", encoding="utf-8")
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            assert load_saved_results("PLA", 0.4, "MK4S") is None

    def test_missing_key(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "results.json"
        fake_path.write_text('{"OTHER|0.4|MK4S": {}}', encoding="utf-8")
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            assert load_saved_results("PLA", 0.4, "MK4S") is None

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "a" / "b" / "results.json"
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            save_results("PLA", 0.4, "MK4S", {"set_temp": True})
            assert fake_path.is_file()
            data = json.loads(fake_path.read_text(encoding="utf-8"))
            assert "PLA|0.4|MK4S" in data

    def test_merges_entries(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "results.json"
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            save_results("PLA", 0.4, "MK4S", {"set_temp": True})
            save_results("PETG", 0.4, "COREONE", {"set_em": True})
            data = json.loads(fake_path.read_text(encoding="utf-8"))
            assert "PLA|0.4|MK4S" in data
            assert "PETG|0.4|COREONE" in data

    def test_non_dict_entry_returns_none(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "results.json"
        fake_path.write_text('{"PLA|0.4|MK4S": "not a dict"}',
                             encoding="utf-8")
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            assert load_saved_results("PLA", 0.4, "MK4S") is None

    def test_save_overwrites_corrupt_file(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "results.json"
        fake_path.write_text("corrupt!", encoding="utf-8")
        with patch(
            "filament_calibrator.gui._results_file_path",
            return_value=fake_path,
        ):
            save_results("PLA", 0.4, "MK4S", {"set_temp": True})
            loaded = load_saved_results("PLA", 0.4, "MK4S")
            assert loaded == {"set_temp": True}

    def test_results_file_path(self) -> None:
        path = _results_file_path()
        assert path.name == "results.json"
        assert "filament-calibrator" in str(path)
