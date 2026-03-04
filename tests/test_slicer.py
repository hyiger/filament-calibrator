"""Tests for filament_calibrator.slicer — PrusaSlicer orchestration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import gcode_lib as gl

from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_SLICER_ARGS,
    DEFAULT_THUMBNAILS,
    VASE_MODE_SLICER_ARGS,
    slice_flow_specimen,
    slice_tower,
)


# ---------------------------------------------------------------------------
# DEFAULT_SLICER_ARGS
# ---------------------------------------------------------------------------


class TestDefaultSlicerArgs:
    def test_has_required_keys(self):
        assert "layer-height" in DEFAULT_SLICER_ARGS
        assert "first-layer-height" in DEFAULT_SLICER_ARGS
        assert "perimeters" in DEFAULT_SLICER_ARGS
        assert "fill-density" in DEFAULT_SLICER_ARGS

    def test_layer_height(self):
        assert DEFAULT_SLICER_ARGS["layer-height"] == "0.2"

    def test_no_support_material_key(self):
        # support-material is a boolean flag in PrusaSlicer; omitting it
        # means "disabled" (the default), so we don't include it.
        assert "support-material" not in DEFAULT_SLICER_ARGS


class TestDefaultThumbnails:
    def test_value(self):
        assert DEFAULT_THUMBNAILS == "16x16,220x124"

    def test_contains_two_sizes(self):
        sizes = DEFAULT_THUMBNAILS.split(",")
        assert len(sizes) == 2
        for size in sizes:
            w, h = size.split("x")
            assert int(w) > 0
            assert int(h) > 0


class TestDefaultBedCenter:
    def test_default_bed_center_format(self):
        assert "," in DEFAULT_BED_CENTER
        x, y = DEFAULT_BED_CENTER.split(",")
        assert int(x) > 0
        assert int(y) > 0

    def test_default_is_mk_series(self):
        assert DEFAULT_BED_CENTER == "125,105"


# ---------------------------------------------------------------------------
# slice_tower
# ---------------------------------------------------------------------------


class TestSliceTower:
    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_with_config_ini(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="ok", stderr=""
        )

        result = slice_tower(
            stl_path="/tmp/tower.stl",
            output_gcode_path="/tmp/tower.gcode",
            config_ini="/path/to/config.ini",
        )

        assert result.ok
        mock_find.assert_called_once_with(explicit_path=None)
        req = mock_slice.call_args[0][1]
        assert req.input_path == "/tmp/tower.stl"
        assert req.output_path == "/tmp/tower.gcode"
        assert req.config_ini == "/path/to/config.ini"
        # With config_ini, default args should NOT be added
        for key, val in DEFAULT_SLICER_ARGS.items():
            assert f"--{key}={val}" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_without_config_ini_uses_defaults(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode")

        req = mock_slice.call_args[0][1]
        assert req.config_ini is None
        # All default args should be present as --key=value
        for key, val in DEFAULT_SLICER_ARGS.items():
            assert f"--{key}={val}" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_custom_prusaslicer_path(self, mock_find, mock_slice):
        mock_find.return_value = "/custom/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     prusaslicer_path="/custom/prusa-slicer")

        mock_find.assert_called_once_with(
            explicit_path="/custom/prusa-slicer"
        )

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extra_args_appended(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini",
                     extra_args=["--nozzle-diameter", "0.4"])

        req = mock_slice.call_args[0][1]
        assert "--nozzle-diameter" in req.extra_args
        assert "0.4" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_failure_result(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=["prusa-slicer"], returncode=1,
            stdout="", stderr="Error: bad config"
        )

        result = slice_tower("/tmp/tower.stl", "/tmp/tower.gcode")
        assert not result.ok
        assert result.returncode == 1

    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_not_found_raises(self, mock_find):
        mock_find.side_effect = FileNotFoundError("not found")

        with pytest.raises(FileNotFoundError):
            slice_tower("/tmp/tower.stl", "/tmp/tower.gcode")

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extra_args_none(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini", extra_args=None)

        req = mock_slice.call_args[0][1]
        # No default slicer args (config_ini provided), no extra_args
        for key, val in DEFAULT_SLICER_ARGS.items():
            assert f"--{key}={val}" not in req.extra_args

    # --- nozzle_temp, bed_temp and fan_speed ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_temp_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini", nozzle_temp=280)

        req = mock_slice.call_args[0][1]
        assert "--temperature=280" in req.extra_args
        assert "--first-layer-temperature=280" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_temp_none_not_added(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini", nozzle_temp=None)

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--temperature=") for a in req.extra_args)
        assert not any(a.startswith("--first-layer-temperature=") for a in req.extra_args)

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_temp_before_bed_temp(self, mock_find, mock_slice):
        """nozzle_temp args appear before bed_temp args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini",
                     nozzle_temp=280, bed_temp=80)

        req = mock_slice.call_args[0][1]
        nozzle_idx = req.extra_args.index("--temperature=280")
        bed_idx = req.extra_args.index("--bed-temperature=80")
        assert nozzle_idx < bed_idx

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bed_temp_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini", bed_temp=80)

        req = mock_slice.call_args[0][1]
        assert "--bed-temperature=80" in req.extra_args
        assert "--first-layer-bed-temperature=80" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_fan_speed_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini", fan_speed=40)

        req = mock_slice.call_args[0][1]
        assert "--max-fan-speed=40" in req.extra_args
        assert "--min-fan-speed=40" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bed_and_fan_with_defaults(self, mock_find, mock_slice):
        """bed_temp/fan_speed are added alongside default slicer args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     bed_temp=60, fan_speed=100)

        req = mock_slice.call_args[0][1]
        # Default args present (no config_ini)
        assert "--layer-height=0.2" in req.extra_args
        # bed/fan also present
        assert "--bed-temperature=60" in req.extra_args
        assert "--max-fan-speed=100" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_none_bed_and_fan_not_added(self, mock_find, mock_slice):
        """When bed_temp/fan_speed are None, they are not added."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini",
                     bed_temp=None, fan_speed=None)

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--bed-temperature") for a in req.extra_args)
        assert not any(a.startswith("--max-fan-speed") for a in req.extra_args)

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extra_args_after_bed_fan(self, mock_find, mock_slice):
        """extra_args come after bed/fan args (can override them)."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini",
                     bed_temp=60, fan_speed=100,
                     extra_args=["--custom", "val"])

        req = mock_slice.call_args[0][1]
        bed_idx = req.extra_args.index("--bed-temperature=60")
        custom_idx = req.extra_args.index("--custom")
        assert custom_idx > bed_idx

    # --- bed_center ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_default_bed_center(self, mock_find, mock_slice):
        """Default bed center is used when bed_center is None."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini")

        req = mock_slice.call_args[0][1]
        assert f"--center={DEFAULT_BED_CENTER}" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_custom_bed_center(self, mock_find, mock_slice):
        """Custom bed_center overrides the default."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini", bed_center="90,90")

        req = mock_slice.call_args[0][1]
        assert "--center=90,90" in req.extra_args
        assert f"--center={DEFAULT_BED_CENTER}" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_center_is_first_arg(self, mock_find, mock_slice):
        """--center appears before other slicer args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     bed_temp=60)

        req = mock_slice.call_args[0][1]
        assert req.extra_args[0] == f"--center={DEFAULT_BED_CENTER}"

    # --- thumbnails ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_thumbnails_in_args(self, mock_find, mock_slice):
        """--thumbnails is always present in slice_tower CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode")

        req = mock_slice.call_args[0][1]
        assert f"--thumbnails={DEFAULT_THUMBNAILS}" in req.extra_args


# ---------------------------------------------------------------------------
# VASE_MODE_SLICER_ARGS
# ---------------------------------------------------------------------------


class TestVaseModeSlicerArgs:
    def test_has_required_keys(self):
        assert "first-layer-height" in VASE_MODE_SLICER_ARGS
        assert "perimeters" in VASE_MODE_SLICER_ARGS
        assert "top-solid-layers" in VASE_MODE_SLICER_ARGS
        assert "bottom-solid-layers" in VASE_MODE_SLICER_ARGS
        assert "fill-density" in VASE_MODE_SLICER_ARGS
        assert "brim-width" in VASE_MODE_SLICER_ARGS

    def test_vase_mode_values(self):
        assert VASE_MODE_SLICER_ARGS["perimeters"] == "1"
        assert VASE_MODE_SLICER_ARGS["top-solid-layers"] == "0"
        assert VASE_MODE_SLICER_ARGS["fill-density"] == "0%"
        assert VASE_MODE_SLICER_ARGS["skirts"] == "0"
        assert VASE_MODE_SLICER_ARGS["brim-width"] == "5"

    def test_no_layer_height(self):
        """layer-height is NOT in VASE_MODE_SLICER_ARGS (set explicitly)."""
        assert "layer-height" not in VASE_MODE_SLICER_ARGS


# ---------------------------------------------------------------------------
# slice_flow_specimen
# ---------------------------------------------------------------------------


class TestSliceFlowSpecimen:
    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_spiral_vase_always_present(self, mock_find, mock_slice):
        """--spiral-vase is always in the CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode")

        req = mock_slice.call_args[0][1]
        assert "--spiral-vase" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_vase_defaults_used_without_config_ini(self, mock_find, mock_slice):
        """VASE_MODE_SLICER_ARGS applied when no config_ini."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode")

        req = mock_slice.call_args[0][1]
        for key, val in VASE_MODE_SLICER_ARGS.items():
            assert f"--{key}={val}" in req.extra_args
        # layer-height and extrusion-width are set explicitly
        assert "--layer-height=0.2" in req.extra_args
        assert "--extrusion-width=0.45" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_no_vase_defaults_with_config_ini(self, mock_find, mock_slice):
        """VASE_MODE_SLICER_ARGS NOT applied when config_ini is given."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/config.ini",
        )

        req = mock_slice.call_args[0][1]
        for key, val in VASE_MODE_SLICER_ARGS.items():
            assert f"--{key}={val}" not in req.extra_args
        # --spiral-vase still present
        assert "--spiral-vase" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_custom_layer_height_and_extrusion_width(self, mock_find, mock_slice):
        """Custom layer_height and extrusion_width are passed."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            layer_height=0.3, extrusion_width=0.6,
        )

        req = mock_slice.call_args[0][1]
        assert "--layer-height=0.3" in req.extra_args
        assert "--extrusion-width=0.6" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_temp_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/config.ini", nozzle_temp=230,
        )

        req = mock_slice.call_args[0][1]
        assert "--temperature=230" in req.extra_args
        assert "--first-layer-temperature=230" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bed_temp_and_fan_speed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/config.ini", bed_temp=80, fan_speed=40,
        )

        req = mock_slice.call_args[0][1]
        assert "--bed-temperature=80" in req.extra_args
        assert "--first-layer-bed-temperature=80" in req.extra_args
        assert "--max-fan-speed=40" in req.extra_args
        assert "--min-fan-speed=40" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_none_temps_not_added(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/config.ini",
            nozzle_temp=None, bed_temp=None, fan_speed=None,
        )

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--temperature=") for a in req.extra_args)
        assert not any(a.startswith("--bed-temperature") for a in req.extra_args)
        assert not any(a.startswith("--max-fan-speed") for a in req.extra_args)

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extra_args_appended(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/config.ini",
            extra_args=["--custom", "val"],
        )

        req = mock_slice.call_args[0][1]
        assert "--custom" in req.extra_args
        assert "val" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_default_bed_center(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode",
                            config_ini="/config.ini")

        req = mock_slice.call_args[0][1]
        assert f"--center={DEFAULT_BED_CENTER}" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_custom_bed_center(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/config.ini", bed_center="90,90",
        )

        req = mock_slice.call_args[0][1]
        assert "--center=90,90" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_custom_prusaslicer_path(self, mock_find, mock_slice):
        mock_find.return_value = "/custom/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            prusaslicer_path="/custom/prusa-slicer",
        )

        mock_find.assert_called_once_with(
            explicit_path="/custom/prusa-slicer"
        )

    # --- thumbnails ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_thumbnails_in_args(self, mock_find, mock_slice):
        """--thumbnails is always present in slice_flow_specimen CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode")

        req = mock_slice.call_args[0][1]
        assert f"--thumbnails={DEFAULT_THUMBNAILS}" in req.extra_args
