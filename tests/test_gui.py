"""Tests for filament_calibrator.gui helper functions."""
from __future__ import annotations

import argparse
import sys

from filament_calibrator.gui import (
    _FALLBACK_PRESET,
    _NOZZLE_SIZES,
    _PRINTER_LIST,
    build_flow_namespace,
    build_pa_namespace,
    build_temp_tower_namespace,
    find_output_file,
    get_preset,
    run_pipeline,
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
            firmware="marlin",
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
        assert ns.firmware == "marlin"
        assert ns.verbose is True

    def test_klipper_firmware(self) -> None:
        ns = build_pa_namespace(
            filament_type="PLA",
            start_pa=0.0,
            end_pa=0.10,
            pa_step=0.01,
            firmware="klipper",
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
        assert ns.firmware == "klipper"


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
