"""Tests for filament_calibrator.slicer — PrusaSlicer orchestration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import gcode_lib as gl

from filament_calibrator.slicer import (
    DEFAULT_BED_CENTER,
    DEFAULT_SLICER_ARGS,
    DEFAULT_THUMBNAILS,
    EM_SLICER_ARGS,
    PA_PATTERN_SLICER_ARGS,
    PA_SLICER_ARGS,
    RETRACTION_SLICER_ARGS,
    VASE_MODE_SLICER_ARGS,
    slice_em_specimen,
    slice_flow_specimen,
    slice_pa_pattern,
    slice_pa_specimen,
    slice_retraction_specimen,
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
        assert DEFAULT_THUMBNAILS == "16x16/PNG,220x124/PNG"

    def test_contains_two_sizes(self):
        sizes = DEFAULT_THUMBNAILS.split(",")
        assert len(sizes) == 2
        for size in sizes:
            # Format: WxH/EXT
            spec, fmt = size.split("/")
            w, h = spec.split("x")
            assert int(w) > 0
            assert int(h) > 0
            assert fmt == "PNG"


class TestDefaultBedCenter:
    def test_default_bed_center_format(self):
        assert "," in DEFAULT_BED_CENTER
        x, y = DEFAULT_BED_CENTER.split(",")
        assert int(x) > 0
        assert int(y) > 0

    def test_default_is_mk_series(self):
        assert DEFAULT_BED_CENTER == "125,110"


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

    # --- nozzle_diameter, layer_height, extrusion_width ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     nozzle_diameter=0.6)

        req = mock_slice.call_args[0][1]
        assert "--nozzle-diameter=0.6" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_layer_height_overrides_defaults(self, mock_find, mock_slice):
        """Custom layer_height replaces DEFAULT_SLICER_ARGS entries."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     layer_height=0.3)

        req = mock_slice.call_args[0][1]
        assert "--layer-height=0.3" in req.extra_args
        assert "--first-layer-height=0.3" in req.extra_args
        # Defaults should NOT be present
        assert "--layer-height=0.2" not in req.extra_args
        assert "--first-layer-height=0.2" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extrusion_width_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     extrusion_width=0.68)

        req = mock_slice.call_args[0][1]
        assert "--extrusion-width=0.68" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_none_nozzle_layer_extrusion_not_added(self, mock_find, mock_slice):
        """None values for nozzle/layer/extrusion are not added."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     config_ini="/config.ini",
                     nozzle_diameter=None, layer_height=None,
                     extrusion_width=None)

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--nozzle-diameter") for a in req.extra_args)
        assert not any(a.startswith("--extrusion-width") for a in req.extra_args)

    # --- binary_gcode ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_default(self, mock_find, mock_slice):
        """binary_gcode defaults to True → --binary-gcode present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode")

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_true(self, mock_find, mock_slice):
        """Explicit binary_gcode=True → --binary-gcode present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     binary_gcode=True)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_false(self, mock_find, mock_slice):
        """binary_gcode=False → --binary-gcode NOT present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     binary_gcode=False)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_printer_model_passed(self, mock_find, mock_slice):
        """printer_model adds --printer-model to CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode",
                     printer_model="COREONE")

        req = mock_slice.call_args[0][1]
        assert "--printer-model=COREONE" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_printer_model_none_omitted(self, mock_find, mock_slice):
        """printer_model=None does not add --printer-model."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_tower("/tmp/tower.stl", "/tmp/tower.gcode")

        req = mock_slice.call_args[0][1]
        for arg in req.extra_args:
            assert not arg.startswith("--printer-model")


# ---------------------------------------------------------------------------
# VASE_MODE_SLICER_ARGS
# ---------------------------------------------------------------------------


class TestVaseModeSlicerArgs:
    def test_has_required_keys(self):
        assert "first-layer-height" in VASE_MODE_SLICER_ARGS
        assert "perimeters" in VASE_MODE_SLICER_ARGS
        assert "top-solid-layers" in VASE_MODE_SLICER_ARGS
        assert "fill-density" in VASE_MODE_SLICER_ARGS

    def test_vase_mode_values(self):
        assert VASE_MODE_SLICER_ARGS["perimeters"] == "1"
        assert VASE_MODE_SLICER_ARGS["top-solid-layers"] == "0"
        assert VASE_MODE_SLICER_ARGS["fill-density"] == "0%"
        assert VASE_MODE_SLICER_ARGS["skirts"] == "0"

    def test_bottom_brim_not_in_dict(self):
        """bottom-solid-layers and brim-width are hardcoded in slice functions."""
        assert "bottom-solid-layers" not in VASE_MODE_SLICER_ARGS
        assert "brim-width" not in VASE_MODE_SLICER_ARGS

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
    def test_supports_disabled_for_vase_mode(self, mock_find, mock_slice):
        """--support-material=0 always present (incompatible with vase)."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode")

        req = mock_slice.call_args[0][1]
        assert "--support-material=0" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bottom_layers_zero_and_brim_always(self, mock_find, mock_slice):
        """--bottom-solid-layers=0 and --brim-width=5 always present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        # With config_ini to ensure they're always applied, not just defaults.
        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/some/config.ini",
        )

        req = mock_slice.call_args[0][1]
        assert "--bottom-solid-layers=0" in req.extra_args
        assert "--brim-width=5" in req.extra_args

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
        """VASE_MODE_SLICER_ARGS NOT applied when config_ini is given
        (except bottom-solid-layers and brim-width which are always forced)."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen(
            "/tmp/specimen.stl", "/tmp/specimen.gcode",
            config_ini="/config.ini",
        )

        # Keys that are always forced for vase mode (not from dict defaults)
        _always_forced = {"bottom-solid-layers", "brim-width"}
        req = mock_slice.call_args[0][1]
        for key, val in VASE_MODE_SLICER_ARGS.items():
            if key in _always_forced:
                continue
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

    # --- nozzle_diameter ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode",
                            nozzle_diameter=0.6)

        req = mock_slice.call_args[0][1]
        assert "--nozzle-diameter=0.6" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter_none_not_added(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode",
                            nozzle_diameter=None)

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--nozzle-diameter") for a in req.extra_args)

    # --- binary_gcode ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_default(self, mock_find, mock_slice):
        """binary_gcode defaults to True → --binary-gcode present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode")

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_true(self, mock_find, mock_slice):
        """Explicit binary_gcode=True → --binary-gcode present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode",
                            binary_gcode=True)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_false(self, mock_find, mock_slice):
        """binary_gcode=False → --binary-gcode NOT present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode",
                            binary_gcode=False)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_printer_model_passed(self, mock_find, mock_slice):
        """printer_model adds --printer-model to CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_flow_specimen("/tmp/specimen.stl", "/tmp/specimen.gcode",
                            printer_model="COREONE")

        req = mock_slice.call_args[0][1]
        assert "--printer-model=COREONE" in req.extra_args


# ---------------------------------------------------------------------------
# PA_SLICER_ARGS
# ---------------------------------------------------------------------------


class TestPASlicerArgs:
    def test_has_required_keys(self):
        assert "first-layer-height" in PA_SLICER_ARGS
        assert "perimeters" in PA_SLICER_ARGS
        assert "top-solid-layers" in PA_SLICER_ARGS
        assert "bottom-solid-layers" in PA_SLICER_ARGS
        assert "fill-density" in PA_SLICER_ARGS
        assert "skirts" in PA_SLICER_ARGS

    def test_pa_values(self):
        assert PA_SLICER_ARGS["perimeters"] == "2"
        assert PA_SLICER_ARGS["top-solid-layers"] == "0"
        assert PA_SLICER_ARGS["bottom-solid-layers"] == "0"
        assert PA_SLICER_ARGS["fill-density"] == "0%"
        assert PA_SLICER_ARGS["skirts"] == "1"

    def test_no_layer_height(self):
        """layer-height is NOT in PA_SLICER_ARGS (set explicitly)."""
        assert "layer-height" not in PA_SLICER_ARGS

    def test_no_brim_width(self):
        """PA tower doesn't use brim (unlike vase-mode flow specimen)."""
        assert "brim-width" not in PA_SLICER_ARGS


# ---------------------------------------------------------------------------
# slice_pa_specimen
# ---------------------------------------------------------------------------


class TestSlicePASpecimen:
    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_pa_defaults_used_without_config_ini(self, mock_find, mock_slice):
        """PA_SLICER_ARGS applied when no config_ini."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode")

        req = mock_slice.call_args[0][1]
        for key, val in PA_SLICER_ARGS.items():
            assert f"--{key}={val}" in req.extra_args
        # layer-height and extrusion-width are set explicitly
        assert "--layer-height=0.2" in req.extra_args
        assert "--extrusion-width=0.45" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_no_pa_defaults_with_config_ini(self, mock_find, mock_slice):
        """PA_SLICER_ARGS NOT applied when config_ini is given."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
            config_ini="/config.ini",
        )

        req = mock_slice.call_args[0][1]
        for key, val in PA_SLICER_ARGS.items():
            assert f"--{key}={val}" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_no_spiral_vase(self, mock_find, mock_slice):
        """PA tower does NOT use --spiral-vase (unlike flow specimen)."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode")

        req = mock_slice.call_args[0][1]
        assert "--spiral-vase" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_custom_layer_height_and_extrusion_width(self, mock_find, mock_slice):
        """Custom layer_height and extrusion_width are passed."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
            layer_height=0.3, extrusion_width=0.68,
        )

        req = mock_slice.call_args[0][1]
        assert "--layer-height=0.3" in req.extra_args
        assert "--extrusion-width=0.68" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_temp_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
            config_ini="/config.ini", nozzle_temp=210,
        )

        req = mock_slice.call_args[0][1]
        assert "--temperature=210" in req.extra_args
        assert "--first-layer-temperature=210" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bed_temp_and_fan_speed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
            config_ini="/config.ini", bed_temp=60, fan_speed=100,
        )

        req = mock_slice.call_args[0][1]
        assert "--bed-temperature=60" in req.extra_args
        assert "--first-layer-bed-temperature=60" in req.extra_args
        assert "--max-fan-speed=100" in req.extra_args
        assert "--min-fan-speed=100" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_none_temps_not_added(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
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

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
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

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
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

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
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

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
            prusaslicer_path="/custom/prusa-slicer",
        )

        mock_find.assert_called_once_with(
            explicit_path="/custom/prusa-slicer"
        )

    # --- thumbnails ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_thumbnails_in_args(self, mock_find, mock_slice):
        """--thumbnails is always present in slice_pa_specimen CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode")

        req = mock_slice.call_args[0][1]
        assert f"--thumbnails={DEFAULT_THUMBNAILS}" in req.extra_args

    # --- nozzle_diameter ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          nozzle_diameter=0.6)

        req = mock_slice.call_args[0][1]
        assert "--nozzle-diameter=0.6" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter_none_not_added(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          nozzle_diameter=None)

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--nozzle-diameter") for a in req.extra_args)

    # --- start_gcode / end_gcode ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_start_gcode_escaped_and_passed(self, mock_find, mock_slice):
        """start_gcode newlines are escaped to literal \\n for PrusaSlicer."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        gcode = "G28\nG29\nM104 S210"
        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          start_gcode=gcode)

        req = mock_slice.call_args[0][1]
        expected = "--start-gcode=G28\\nG29\\nM104 S210"
        assert expected in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_end_gcode_escaped_and_passed(self, mock_find, mock_slice):
        """end_gcode newlines are escaped to literal \\n for PrusaSlicer."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        gcode = "M104 S0\nM140 S0\nG28 X"
        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          end_gcode=gcode)

        req = mock_slice.call_args[0][1]
        expected = "--end-gcode=M104 S0\\nM140 S0\\nG28 X"
        assert expected in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_start_and_end_gcode_both_passed(self, mock_find, mock_slice):
        """Both start_gcode and end_gcode can be passed simultaneously."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen(
            "/tmp/pa.stl", "/tmp/pa.gcode",
            start_gcode="G28\nG29",
            end_gcode="M104 S0\nG28",
        )

        req = mock_slice.call_args[0][1]
        assert "--start-gcode=G28\\nG29" in req.extra_args
        assert "--end-gcode=M104 S0\\nG28" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_none_gcode_not_added(self, mock_find, mock_slice):
        """start_gcode=None and end_gcode=None are not added."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          start_gcode=None, end_gcode=None)

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--start-gcode") for a in req.extra_args)
        assert not any(a.startswith("--end-gcode") for a in req.extra_args)

    # --- binary_gcode ---

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_default(self, mock_find, mock_slice):
        """binary_gcode defaults to True → --binary-gcode present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode")

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_true(self, mock_find, mock_slice):
        """Explicit binary_gcode=True → --binary-gcode present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          binary_gcode=True)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_false(self, mock_find, mock_slice):
        """binary_gcode=False → --binary-gcode NOT present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          binary_gcode=False)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_printer_model_passed(self, mock_find, mock_slice):
        """printer_model adds --printer-model to CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_specimen("/tmp/pa.stl", "/tmp/pa.gcode",
                          printer_model="COREONE")

        req = mock_slice.call_args[0][1]
        assert "--printer-model=COREONE" in req.extra_args


# ---------------------------------------------------------------------------
# PA_PATTERN_SLICER_ARGS
# ---------------------------------------------------------------------------


class TestPAPatternSlicerArgs:
    def test_has_required_keys(self):
        assert "first-layer-height" in PA_PATTERN_SLICER_ARGS
        assert "top-solid-layers" in PA_PATTERN_SLICER_ARGS
        assert "bottom-solid-layers" in PA_PATTERN_SLICER_ARGS
        assert "fill-density" in PA_PATTERN_SLICER_ARGS
        assert "skirts" in PA_PATTERN_SLICER_ARGS

    def test_no_perimeters_key(self):
        """perimeters NOT included — set explicitly by slice_pa_pattern."""
        assert "perimeters" not in PA_PATTERN_SLICER_ARGS

    def test_no_layer_height(self):
        """layer-height NOT included — set explicitly."""
        assert "layer-height" not in PA_PATTERN_SLICER_ARGS

    def test_values(self):
        assert PA_PATTERN_SLICER_ARGS["top-solid-layers"] == "0"
        assert PA_PATTERN_SLICER_ARGS["bottom-solid-layers"] == "0"
        assert PA_PATTERN_SLICER_ARGS["fill-density"] == "0%"
        assert PA_PATTERN_SLICER_ARGS["skirts"] == "1"


# ---------------------------------------------------------------------------
# slice_pa_pattern
# ---------------------------------------------------------------------------


class TestSlicePAPattern:
    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_pattern_defaults_used_without_config_ini(self, mock_find, mock_slice):
        """PA_PATTERN_SLICER_ARGS applied when no config_ini."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode")

        req = mock_slice.call_args[0][1]
        for key, val in PA_PATTERN_SLICER_ARGS.items():
            assert f"--{key}={val}" in req.extra_args
        assert "--perimeters=3" in req.extra_args
        assert "--layer-height=0.2" in req.extra_args
        assert "--extrusion-width=0.45" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_custom_perimeters(self, mock_find, mock_slice):
        """Custom perimeters parameter is passed."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode", perimeters=5)

        req = mock_slice.call_args[0][1]
        assert "--perimeters=5" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_no_pattern_defaults_with_config_ini(self, mock_find, mock_slice):
        """PA_PATTERN_SLICER_ARGS NOT applied when config_ini is given."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern(
            "/tmp/pat.stl", "/tmp/pat.gcode",
            config_ini="/config.ini",
        )

        req = mock_slice.call_args[0][1]
        for key, val in PA_PATTERN_SLICER_ARGS.items():
            assert f"--{key}={val}" not in req.extra_args
        # perimeters also not set when config_ini provided
        assert not any(a.startswith("--perimeters") for a in req.extra_args)

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_no_spiral_vase(self, mock_find, mock_slice):
        """PA pattern does NOT use --spiral-vase."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode")

        req = mock_slice.call_args[0][1]
        assert "--spiral-vase" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_temps_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern(
            "/tmp/pat.stl", "/tmp/pat.gcode",
            nozzle_temp=215, bed_temp=60, fan_speed=100,
        )

        req = mock_slice.call_args[0][1]
        assert "--temperature=215" in req.extra_args
        assert "--bed-temperature=60" in req.extra_args
        assert "--max-fan-speed=100" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_start_end_gcode_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern(
            "/tmp/pat.stl", "/tmp/pat.gcode",
            start_gcode="G28\nG29", end_gcode="M104 S0",
        )

        req = mock_slice.call_args[0][1]
        assert "--start-gcode=G28\\nG29" in req.extra_args
        assert "--end-gcode=M104 S0" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_default(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode")

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_false(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode",
                         binary_gcode=False)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_thumbnails_in_args(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode")

        req = mock_slice.call_args[0][1]
        assert f"--thumbnails={DEFAULT_THUMBNAILS}" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_printer_model_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode",
                         printer_model="MK4S")

        req = mock_slice.call_args[0][1]
        assert "--printer-model=MK4S" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extra_args_appended(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern(
            "/tmp/pat.stl", "/tmp/pat.gcode",
            extra_args=["--custom", "val"],
        )

        req = mock_slice.call_args[0][1]
        assert "--custom" in req.extra_args
        assert "val" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_pa_pattern("/tmp/pat.stl", "/tmp/pat.gcode",
                         nozzle_diameter=0.6)

        req = mock_slice.call_args[0][1]
        assert "--nozzle-diameter=0.6" in req.extra_args


# ---------------------------------------------------------------------------
# EM_SLICER_ARGS
# ---------------------------------------------------------------------------


class TestEmSlicerArgs:
    def test_has_required_keys(self):
        assert "first-layer-height" in EM_SLICER_ARGS
        assert "perimeters" in EM_SLICER_ARGS
        assert "top-solid-layers" in EM_SLICER_ARGS
        assert "fill-density" in EM_SLICER_ARGS

    def test_em_values(self):
        assert EM_SLICER_ARGS["perimeters"] == "1"
        assert EM_SLICER_ARGS["top-solid-layers"] == "0"
        assert EM_SLICER_ARGS["fill-density"] == "0%"
        assert EM_SLICER_ARGS["skirts"] == "0"

    def test_bottom_brim_not_in_dict(self):
        """bottom-solid-layers and brim-width are hardcoded in slice_em_specimen."""
        assert "bottom-solid-layers" not in EM_SLICER_ARGS
        assert "brim-width" not in EM_SLICER_ARGS

    def test_no_layer_height(self):
        """layer-height is NOT in EM_SLICER_ARGS (set explicitly)."""
        assert "layer-height" not in EM_SLICER_ARGS


# ---------------------------------------------------------------------------
# slice_em_specimen
# ---------------------------------------------------------------------------


class TestSliceEmSpecimen:
    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_spiral_vase_always_present(self, mock_find, mock_slice):
        """--spiral-vase is always in the CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode")

        req = mock_slice.call_args[0][1]
        assert "--spiral-vase" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_perimeter_generator_classic(self, mock_find, mock_slice):
        """--perimeter-generator=classic is always in the CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode")

        req = mock_slice.call_args[0][1]
        assert "--perimeter-generator=classic" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_supports_disabled(self, mock_find, mock_slice):
        """--support-material=0 always present (incompatible with vase)."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode")

        req = mock_slice.call_args[0][1]
        assert "--support-material=0" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bottom_layers_zero_and_brim_always(self, mock_find, mock_slice):
        """--bottom-solid-layers=0 and --brim-width=5 always present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        # With config_ini to ensure they're always applied.
        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
            config_ini="/some/config.ini",
        )

        req = mock_slice.call_args[0][1]
        assert "--bottom-solid-layers=0" in req.extra_args
        assert "--brim-width=5" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_em_defaults_used_without_config_ini(self, mock_find, mock_slice):
        """EM_SLICER_ARGS applied when no config_ini."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode")

        req = mock_slice.call_args[0][1]
        for key, val in EM_SLICER_ARGS.items():
            assert f"--{key}={val}" in req.extra_args
        assert "--layer-height=0.2" in req.extra_args
        assert "--extrusion-width=0.45" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_no_em_defaults_with_config_ini(self, mock_find, mock_slice):
        """EM_SLICER_ARGS NOT applied when config_ini is given
        (except bottom-solid-layers and brim-width which are always forced)."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
            config_ini="/config.ini",
        )

        _always_forced = {"bottom-solid-layers", "brim-width"}
        req = mock_slice.call_args[0][1]
        for key, val in EM_SLICER_ARGS.items():
            if key in _always_forced:
                continue
            assert f"--{key}={val}" not in req.extra_args
        # --spiral-vase and --perimeter-generator still present
        assert "--spiral-vase" in req.extra_args
        assert "--perimeter-generator=classic" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_temp_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
            config_ini="/config.ini", nozzle_temp=210,
        )

        req = mock_slice.call_args[0][1]
        assert "--temperature=210" in req.extra_args
        assert "--first-layer-temperature=210" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bed_temp_and_fan_speed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
            config_ini="/config.ini", bed_temp=60, fan_speed=100,
        )

        req = mock_slice.call_args[0][1]
        assert "--bed-temperature=60" in req.extra_args
        assert "--first-layer-bed-temperature=60" in req.extra_args
        assert "--max-fan-speed=100" in req.extra_args
        assert "--min-fan-speed=100" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_none_temps_not_added(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
            config_ini="/config.ini",
            nozzle_temp=None, bed_temp=None, fan_speed=None,
        )

        req = mock_slice.call_args[0][1]
        assert not any(a.startswith("--temperature=") for a in req.extra_args)
        assert not any(a.startswith("--bed-temperature") for a in req.extra_args)
        assert not any(a.startswith("--max-fan-speed") for a in req.extra_args)

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_default_bed_center(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode",
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

        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
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

        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
            prusaslicer_path="/custom/prusa-slicer",
        )

        mock_find.assert_called_once_with(
            explicit_path="/custom/prusa-slicer"
        )

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_thumbnails_in_args(self, mock_find, mock_slice):
        """--thumbnails is always present in slice_em_specimen CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode")

        req = mock_slice.call_args[0][1]
        assert f"--thumbnails={DEFAULT_THUMBNAILS}" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode",
                          nozzle_diameter=0.6)

        req = mock_slice.call_args[0][1]
        assert "--nozzle-diameter=0.6" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_default(self, mock_find, mock_slice):
        """binary_gcode defaults to True → --binary-gcode present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode")

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_false(self, mock_find, mock_slice):
        """binary_gcode=False → --binary-gcode NOT present."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode",
                          binary_gcode=False)

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_printer_model_passed(self, mock_find, mock_slice):
        """printer_model adds --printer-model to CLI args."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen("/tmp/cube.stl", "/tmp/cube.gcode",
                          printer_model="COREONE")

        req = mock_slice.call_args[0][1]
        assert "--printer-model=COREONE" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extra_args_appended(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_em_specimen(
            "/tmp/cube.stl", "/tmp/cube.gcode",
            config_ini="/config.ini",
            extra_args=["--custom", "val"],
        )

        req = mock_slice.call_args[0][1]
        assert "--custom" in req.extra_args
        assert "val" in req.extra_args


# ---------------------------------------------------------------------------
# RETRACTION_SLICER_ARGS
# ---------------------------------------------------------------------------


class TestRetractionSlicerArgs:
    def test_has_required_keys(self):
        assert "first-layer-height" in RETRACTION_SLICER_ARGS
        assert "perimeters" in RETRACTION_SLICER_ARGS
        assert "fill-density" in RETRACTION_SLICER_ARGS

    def test_two_perimeters(self):
        assert RETRACTION_SLICER_ARGS["perimeters"] == "2"

    def test_no_layer_height_key(self):
        # layer-height is passed explicitly by slice_retraction_specimen
        assert "layer-height" not in RETRACTION_SLICER_ARGS


# ---------------------------------------------------------------------------
# slice_retraction_specimen
# ---------------------------------------------------------------------------


class TestSliceRetractionSpecimen:
    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_with_config_ini(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="ok", stderr=""
        )

        result = slice_retraction_specimen(
            stl_path="/tmp/tower.stl",
            output_gcode_path="/tmp/tower.gcode",
            config_ini="/path/to/config.ini",
        )

        assert result.ok
        req = mock_slice.call_args[0][1]
        assert req.config_ini == "/path/to/config.ini"
        # With config_ini, default slicer args should NOT be added
        for key in RETRACTION_SLICER_ARGS:
            assert f"--{key}" not in " ".join(req.extra_args)

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_without_config_ini(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="ok", stderr=""
        )

        slice_retraction_specimen(
            stl_path="/tmp/tower.stl",
            output_gcode_path="/tmp/tower.gcode",
        )

        req = mock_slice.call_args[0][1]
        # Default args should be applied
        for key, val in RETRACTION_SLICER_ARGS.items():
            assert f"--{key}={val}" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_firmware_retraction_always_enabled(self, mock_find, mock_slice):
        """--use-firmware-retraction and --wipe=0 always added."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        # Without config_ini
        slice_retraction_specimen("/tmp/t.stl", "/tmp/t.gcode")
        req = mock_slice.call_args[0][1]
        assert "--use-firmware-retraction" in req.extra_args
        assert "--wipe=0" in req.extra_args

        # With config_ini
        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode", config_ini="/c.ini",
        )
        req = mock_slice.call_args[0][1]
        assert "--use-firmware-retraction" in req.extra_args
        assert "--wipe=0" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_layer_height_and_extrusion_width(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode",
            layer_height=0.3, extrusion_width=0.68,
        )

        req = mock_slice.call_args[0][1]
        assert "--layer-height=0.3" in req.extra_args
        assert "--extrusion-width=0.68" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_temp_bed_fan(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode",
            nozzle_temp=230, bed_temp=80, fan_speed=50,
        )

        req = mock_slice.call_args[0][1]
        assert "--temperature=230" in req.extra_args
        assert "--first-layer-temperature=230" in req.extra_args
        assert "--bed-temperature=80" in req.extra_args
        assert "--first-layer-bed-temperature=80" in req.extra_args
        assert "--max-fan-speed=50" in req.extra_args
        assert "--min-fan-speed=50" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bed_center_default(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen("/tmp/t.stl", "/tmp/t.gcode")

        req = mock_slice.call_args[0][1]
        assert f"--center={DEFAULT_BED_CENTER}" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_bed_center_custom(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode", bed_center="90,90",
        )

        req = mock_slice.call_args[0][1]
        assert "--center=90,90" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_nozzle_diameter(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode", nozzle_diameter=0.6,
        )

        req = mock_slice.call_args[0][1]
        assert "--nozzle-diameter=0.6" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_default(self, mock_find, mock_slice):
        """binary_gcode defaults to True."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen("/tmp/t.stl", "/tmp/t.gcode")

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_binary_gcode_false(self, mock_find, mock_slice):
        """binary_gcode=False → no --binary-gcode."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode", binary_gcode=False,
        )

        req = mock_slice.call_args[0][1]
        assert "--binary-gcode" not in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_printer_model_passed(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode", printer_model="COREONE",
        )

        req = mock_slice.call_args[0][1]
        assert "--printer-model=COREONE" in req.extra_args

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_start_end_gcode(self, mock_find, mock_slice):
        """start_gcode and end_gcode are escaped and passed."""
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode",
            start_gcode="G28\nG1 Z5",
            end_gcode="M84\n",
        )

        req = mock_slice.call_args[0][1]
        start_args = [a for a in req.extra_args if a.startswith("--start-gcode")]
        end_args = [a for a in req.extra_args if a.startswith("--end-gcode")]
        assert len(start_args) == 1
        assert len(end_args) == 1
        assert "\\n" in start_args[0]

    @patch("filament_calibrator.slicer.gl.slice_model")
    @patch("filament_calibrator.slicer.gl.find_prusaslicer_executable")
    def test_extra_args_appended_retraction(self, mock_find, mock_slice):
        mock_find.return_value = "/usr/bin/prusa-slicer"
        mock_slice.return_value = gl.RunResult(
            cmd=[], returncode=0, stdout="", stderr=""
        )

        slice_retraction_specimen(
            "/tmp/t.stl", "/tmp/t.gcode",
            config_ini="/config.ini",
            extra_args=["--custom", "val"],
        )

        req = mock_slice.call_args[0][1]
        assert "--custom" in req.extra_args
        assert "val" in req.extra_args
