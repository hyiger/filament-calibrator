"""Tests for filament_calibrator.gui helper functions."""
from __future__ import annotations

import argparse
import subprocess
import sys
from unittest.mock import MagicMock, patch

from filament_calibrator.gui import (
    _FALLBACK_PRESET,
    _NOZZLE_SIZES,
    _PRINTER_LIST,
    _fresh_output_dir,
    _open_directory_dialog,
    _open_file_dialog,
    _osascript_directory_dialog,
    _osascript_file_dialog,
    _run_osascript,
    _tkinter_directory_dialog,
    _tkinter_file_dialog,
    apply_ini_to_session,
    apply_toml_to_session,
    build_calibration_results,
    build_em_namespace,
    build_flow_namespace,
    build_pa_namespace,
    build_temp_tower_namespace,
    find_output_file,
    get_preset,
    run_pipeline,
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
        }
        apply_ini_to_session(state, ini_vals)

        # Nozzle temp → EM + flow + PA tabs.
        assert state["em_nozzle_temp"] == 220
        assert state["flow_nozzle_temp"] == 220
        assert state["pa_nozzle_temp"] == 220

        # Bed temp → all four tabs.
        assert state["tt_bed_temp"] == 65
        assert state["em_bed_temp"] == 65
        assert state["flow_bed_temp"] == 65
        assert state["pa_bed_temp"] == 65

        # Fan speed → all four tabs.
        assert state["tt_fan"] == 80
        assert state["em_fan"] == 80
        assert state["flow_fan"] == 80
        assert state["pa_fan"] == 80

        # Layer height / extrusion width → EM + flow + PA.
        assert state["em_lh"] == 0.15
        assert state["flow_lh"] == 0.15
        assert state["pa_lh"] == 0.15
        assert state["em_ew"] == 0.45
        assert state["flow_ew"] == 0.45
        assert state["pa_ew"] == 0.45

        # Selectbox widget keys (written directly for Streamlit key= binding).
        assert state["sidebar_nozzle_size"] == 0.4
        assert state["sidebar_printer"] == "COREONE"

    def test_partial_dict_only_temp(self) -> None:
        state: dict = {}
        apply_ini_to_session(state, {"nozzle_temp": 210})
        assert state["em_nozzle_temp"] == 210
        assert state["flow_nozzle_temp"] == 210
        assert state["pa_nozzle_temp"] == 210
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

    def test_sidebar_false_skips_sidebar_keys(self) -> None:
        """sidebar=False skips sidebar widget keys (post-render re-apply)."""
        state: dict = {}
        ini_vals = {
            "nozzle_temp": 230,
            "bed_temp": 70,
            "nozzle_diameter": 0.6,
            "printer_model": "COREONE",
            "filament_type": "PETG",
        }
        apply_ini_to_session(state, ini_vals, sidebar=False)
        # Tab keys are written.
        assert state["em_nozzle_temp"] == 230
        assert state["pa_bed_temp"] == 70
        # Sidebar keys are NOT written.
        assert "sidebar_nozzle_size" not in state
        assert "sidebar_printer" not in state
        assert "sidebar_filament_type" not in state


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
            printer="COREONE",
        )
        assert r.temperature == 215
        assert r.max_volumetric_speed == 12.5
        assert r.pa_value == 0.04
        assert r.extrusion_multiplier == 0.95
        assert r.printer == "COREONE"

    def test_none_set(self) -> None:
        r = build_calibration_results(
            set_temp=False, temperature=215,
            set_flow=False, max_volumetric_speed=12.5,
            set_pa=False, pa_value=0.04,
            set_em=False, extrusion_multiplier=0.95,
            printer="COREONE",
        )
        assert r.temperature is None
        assert r.max_volumetric_speed is None
        assert r.pa_value is None
        assert r.extrusion_multiplier is None
        assert r.printer == "COREONE"

    def test_partial_temp_only(self) -> None:
        r = build_calibration_results(
            set_temp=True, temperature=230,
            set_flow=False, max_volumetric_speed=11.0,
            set_pa=False, pa_value=0.04,
            set_em=False, extrusion_multiplier=1.0,
            printer="MINI",
        )
        assert r.temperature == 230
        assert r.max_volumetric_speed is None
        assert r.pa_value is None
        assert r.extrusion_multiplier is None
        assert r.printer == "MINI"

    def test_partial_em_only(self) -> None:
        r = build_calibration_results(
            set_temp=False, temperature=215,
            set_flow=False, max_volumetric_speed=11.0,
            set_pa=False, pa_value=0.04,
            set_em=True, extrusion_multiplier=0.97,
            printer="COREONE",
        )
        assert r.temperature is None
        assert r.extrusion_multiplier == 0.97
