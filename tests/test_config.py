"""Tests for filament_calibrator.config — TOML config loading."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from filament_calibrator.config import (
    CONFIG_KEYS,
    _KEY_TO_ATTR,
    _find_config_path,
    load_config,
)


# ---------------------------------------------------------------------------
# tomli fallback import
# ---------------------------------------------------------------------------


class TestTomlImportFallback:
    def test_falls_back_to_tomli(self):
        """When tomllib is unavailable, the module imports tomli instead."""
        import types
        import filament_calibrator.config as cfg_mod

        # Provide a fake tomli module and block tomllib
        fake_tomli = types.ModuleType("tomli")
        fake_tomli.load = lambda f: {}  # type: ignore[attr-defined]

        saved_tomllib = sys.modules.get("tomllib")
        # Setting to None makes import raise ImportError
        sys.modules["tomllib"] = None  # type: ignore[assignment]
        sys.modules["tomli"] = fake_tomli
        try:
            importlib.reload(cfg_mod)
            # After reload, cfg_mod.tomllib should be the fake tomli
            assert cfg_mod.tomllib is fake_tomli
        finally:
            # Restore
            sys.modules.pop("tomli", None)
            if saved_tomllib is not None:
                sys.modules["tomllib"] = saved_tomllib
            else:
                sys.modules.pop("tomllib", None)
            importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# CONFIG_KEYS / _KEY_TO_ATTR
# ---------------------------------------------------------------------------


class TestConstants:
    def test_config_keys_is_frozenset(self):
        assert isinstance(CONFIG_KEYS, frozenset)

    def test_expected_keys(self):
        expected = {
            "printer-url", "api-key", "prusaslicer-path",
            "config-ini", "filament-type", "output-dir",
            "bed-center", "nozzle-size", "printer",
        }
        assert CONFIG_KEYS == expected

    def test_key_to_attr_mapping(self):
        assert _KEY_TO_ATTR["printer-url"] == "printer_url"
        assert _KEY_TO_ATTR["api-key"] == "api_key"
        assert _KEY_TO_ATTR["filament-type"] == "filament_type"
        assert _KEY_TO_ATTR["config-ini"] == "config_ini"
        assert _KEY_TO_ATTR["prusaslicer-path"] == "prusaslicer_path"
        assert _KEY_TO_ATTR["output-dir"] == "output_dir"
        assert _KEY_TO_ATTR["bed-center"] == "bed_center"
        assert _KEY_TO_ATTR["nozzle-size"] == "nozzle_size"

    def test_key_to_attr_covers_all_keys(self):
        assert set(_KEY_TO_ATTR.keys()) == CONFIG_KEYS


# ---------------------------------------------------------------------------
# _find_config_path
# ---------------------------------------------------------------------------


class TestFindConfigPath:
    def test_explicit_path_found(self, tmp_path):
        cfg = tmp_path / "my.toml"
        cfg.write_text("")
        assert _find_config_path(str(cfg)) == cfg

    def test_explicit_path_missing_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            _find_config_path(str(tmp_path / "nope.toml"))

    def test_local_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / "filament-calibrator.toml"
        local.write_text("")
        result = _find_config_path()
        assert result.resolve() == local.resolve()

    def test_xdg_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no local file here
        xdg = tmp_path / ".config" / "filament-calibrator" / "config.toml"
        xdg.parent.mkdir(parents=True)
        xdg.write_text("")
        with patch("filament_calibrator.config.Path.home", return_value=tmp_path):
            assert _find_config_path() == xdg

    def test_local_takes_precedence_over_xdg(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / "filament-calibrator.toml"
        local.write_text("")
        xdg = tmp_path / ".config" / "filament-calibrator" / "config.toml"
        xdg.parent.mkdir(parents=True)
        xdg.write_text("")
        # local should win even if XDG exists
        result = _find_config_path()
        assert result.resolve() == local.resolve()

    def test_no_file_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("filament_calibrator.config.Path.home", return_value=tmp_path):
            assert _find_config_path() is None


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_valid_config(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            'printer-url = "http://10.0.0.1"\n'
            'api-key = "secret"\n'
            'filament-type = "PETG"\n'
        )
        result = load_config(str(cfg))
        assert result == {
            "printer_url": "http://10.0.0.1",
            "api_key": "secret",
            "filament_type": "PETG",
        }

    def test_load_all_keys(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            'printer-url = "http://10.0.0.1"\n'
            'api-key = "secret"\n'
            'prusaslicer-path = "/usr/bin/ps"\n'
            'config-ini = "/path/to/profile.ini"\n'
            'filament-type = "ABS"\n'
            'output-dir = "/tmp/out"\n'
        )
        result = load_config(str(cfg))
        assert len(result) == 6
        assert result["prusaslicer_path"] == "/usr/bin/ps"
        assert result["config_ini"] == "/path/to/profile.ini"
        assert result["output_dir"] == "/tmp/out"

    def test_empty_file(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("")
        assert load_config(str(cfg)) == {}

    def test_unknown_key_warns(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text('bogus-key = "value"\n')
        with pytest.warns(UserWarning, match="unknown config key"):
            result = load_config(str(cfg))
        assert result == {}

    def test_no_config_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("filament_calibrator.config.Path.home", return_value=tmp_path):
            assert load_config() == {}

    def test_explicit_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            load_config(str(tmp_path / "missing.toml"))

    def test_wrong_type_string_for_float_warns(self, tmp_path):
        """String value for a float key emits a warning and is ignored."""
        cfg = tmp_path / "config.toml"
        cfg.write_text('nozzle-size = "big"\n')
        with pytest.warns(UserWarning, match="expected float"):
            result = load_config(str(cfg))
        assert result == {}

    def test_int_value_for_float_key_accepted(self, tmp_path):
        """Integer value for a float key is silently promoted to float."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("nozzle-size = 1\n")
        result = load_config(str(cfg))
        assert result == {"nozzle_size": 1.0}
        assert isinstance(result["nozzle_size"], float)

    def test_wrong_type_int_for_string_warns(self, tmp_path):
        """Integer value for a string key emits a warning and is ignored."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("filament-type = 42\n")
        with pytest.warns(UserWarning, match="expected str"):
            result = load_config(str(cfg))
        assert result == {}

    def test_bool_for_string_key_warns(self, tmp_path):
        """Boolean value for a string key emits a warning and is ignored."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("printer = true\n")
        with pytest.warns(UserWarning, match="expected str"):
            result = load_config(str(cfg))
        assert result == {}

    def test_mixed_valid_and_invalid_types(self, tmp_path):
        """Valid keys are loaded; invalid-type keys are skipped with a warning."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            'printer-url = "http://10.0.0.1"\n'
            "nozzle-size = true\n"
        )
        with pytest.warns(UserWarning, match="expected float"):
            result = load_config(str(cfg))
        assert result == {"printer_url": "http://10.0.0.1"}
