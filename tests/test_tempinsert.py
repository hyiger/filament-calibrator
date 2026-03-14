"""Tests for filament_calibrator.tempinsert — temperature G-code insertion."""
from __future__ import annotations

import pytest

from tests.helpers import parse_gcode as _lines, raw_texts as _raw_texts

from filament_calibrator.model import BASE_HEIGHT, TIER_HEIGHT
from filament_calibrator.tempinsert import (
    TempTier,
    compute_temp_tiers,
    insert_temperatures,
    _tier_for_z,
)


# ---------------------------------------------------------------------------
# TempTier
# ---------------------------------------------------------------------------


class TestTempTier:
    def test_attributes(self):
        t = TempTier(temp=215, z_start=1.0, z_end=11.0)
        assert t.temp == 215
        assert t.z_start == 1.0
        assert t.z_end == 11.0


# ---------------------------------------------------------------------------
# compute_temp_tiers
# ---------------------------------------------------------------------------


class TestComputeTempTiers:
    def test_default_nine_tiers(self):
        tiers = compute_temp_tiers(220, 10, 9)
        assert len(tiers) == 9
        assert tiers[0].temp == 220
        assert tiers[0].z_start == pytest.approx(1.0)
        assert tiers[0].z_end == pytest.approx(11.0)
        assert tiers[8].temp == 140
        assert tiers[8].z_start == pytest.approx(81.0)
        assert tiers[8].z_end == pytest.approx(91.0)

    def test_single_tier(self):
        tiers = compute_temp_tiers(200, 5, 1)
        assert len(tiers) == 1
        assert tiers[0].temp == 200
        assert tiers[0].z_start == pytest.approx(1.0)
        assert tiers[0].z_end == pytest.approx(11.0)

    def test_custom_heights(self):
        tiers = compute_temp_tiers(230, 10, 3,
                                   base_height=2.0, tier_height=5.0)
        assert tiers[0].z_start == pytest.approx(2.0)
        assert tiers[0].z_end == pytest.approx(7.0)
        assert tiers[1].z_start == pytest.approx(7.0)
        assert tiers[1].z_end == pytest.approx(12.0)
        assert tiers[2].z_start == pytest.approx(12.0)
        assert tiers[2].z_end == pytest.approx(17.0)
        assert tiers[0].temp == 230
        assert tiers[1].temp == 220
        assert tiers[2].temp == 210

    def test_zero_tiers(self):
        tiers = compute_temp_tiers(200, 10, 0)
        assert tiers == []

    def test_default_constants(self):
        assert BASE_HEIGHT == pytest.approx(1.0)
        assert TIER_HEIGHT == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# _tier_for_z
# ---------------------------------------------------------------------------


class TestTierForZ:
    def test_in_first_tier(self):
        tiers = compute_temp_tiers(220, 10, 3)
        assert _tier_for_z(5.0, tiers).temp == 220

    def test_in_second_tier(self):
        tiers = compute_temp_tiers(220, 10, 3)
        assert _tier_for_z(15.0, tiers).temp == 210

    def test_at_tier_boundary(self):
        tiers = compute_temp_tiers(220, 10, 3)
        # z_end is inclusive — boundary layer belongs to current tier
        assert _tier_for_z(11.0, tiers).temp == 220

    def test_below_first_tier(self):
        tiers = compute_temp_tiers(220, 10, 3)
        assert _tier_for_z(0.5, tiers) is None

    def test_above_last_tier(self):
        tiers = compute_temp_tiers(220, 10, 3)
        assert _tier_for_z(31.5, tiers) is None

    def test_empty_tiers(self):
        assert _tier_for_z(5.0, []) is None


# ---------------------------------------------------------------------------
# insert_temperatures
# ---------------------------------------------------------------------------


class TestInsertTemperatures:
    def test_basic_insertion(self):
        """M104 commands are inserted at tier boundaries."""
        gcode = (
            "G28\n"
            "G1 Z0.2 F1000\n"        # base layer
            "G1 X10 E1\n"
            "G1 Z1.2 F1000\n"        # tier 0 starts (z=1.2 > base_height=1.0)
            "G1 X20 E2\n"
            "G1 Z11.2 F1000\n"       # tier 1 starts (z=11.2 > 11.0)
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        tiers = compute_temp_tiers(220, 10, 2)
        result = insert_temperatures(lines, tiers)
        texts = _raw_texts(result)

        # Should have M104 S220 before tier 0 and M104 S210 before tier 1
        m104_lines = [t for t in texts if t.startswith("M104")]
        assert len(m104_lines) == 2
        assert "S220" in m104_lines[0]
        assert "S210" in m104_lines[1]

    def test_base_gets_first_tier_temp(self):
        """Base plate layers should get the first tier's temperature."""
        gcode = (
            "G1 Z0.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z1.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        tiers = compute_temp_tiers(230, 5, 2)
        result = insert_temperatures(lines, tiers)
        texts = _raw_texts(result)

        # First M104 should be for the base at 230
        m104_lines = [t for t in texts if t.startswith("M104")]
        assert len(m104_lines) >= 1
        assert "S230" in m104_lines[0]

    def test_no_duplicate_temps(self):
        """Same-temp layers don't get duplicate M104 commands."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z1.4 F1000\n"   # still in tier 0
            "G1 X20 E2\n"
            "G1 Z5.0 F1000\n"   # still in tier 0
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        tiers = compute_temp_tiers(220, 10, 2)
        result = insert_temperatures(lines, tiers)
        texts = _raw_texts(result)

        m104_lines = [t for t in texts if t.startswith("M104")]
        assert len(m104_lines) == 1
        assert "S220" in m104_lines[0]

    def test_empty_tiers_no_insertion(self):
        gcode = "G28\nG1 X10 E1\n"
        lines = _lines(gcode)
        result = insert_temperatures(lines, [])
        assert len(result) == len(lines)

    def test_empty_lines(self):
        result = insert_temperatures([], compute_temp_tiers(220, 10, 3))
        assert result == []

    def test_m104_order_in_output(self):
        """M104 appears before the first line of the new-tier layer."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z11.2 F1000\n"
            "G1 X20 E2\n"
        )
        lines = _lines(gcode)
        tiers = compute_temp_tiers(220, 10, 2)
        result = insert_temperatures(lines, tiers)
        texts = _raw_texts(result)

        # Find indices (use default=-1 so missing values fail with a clear assertion)
        idx_m104_220 = next((i for i, t in enumerate(texts) if "S220" in t), -1)
        idx_z1_2 = next((i for i, t in enumerate(texts) if "Z1.2" in t), -1)
        assert idx_m104_220 != -1, "M104 S220 not found in output"
        assert idx_z1_2 != -1, "Z1.2 move not found in output"
        assert idx_m104_220 < idx_z1_2

        idx_m104_210 = next((i for i, t in enumerate(texts) if "S210" in t), -1)
        idx_z11_2 = next((i for i, t in enumerate(texts) if "Z11.2" in t), -1)
        assert idx_m104_210 != -1, "M104 S210 not found in output"
        assert idx_z11_2 != -1, "Z11.2 move not found in output"
        assert idx_m104_210 < idx_z11_2

    def test_above_last_tier_keeps_temp(self):
        """Layers above the last tier don't generate new M104 commands."""
        gcode = (
            "G1 Z1.2 F1000\n"
            "G1 X10 E1\n"
            "G1 Z11.2 F1000\n"
            "G1 X20 E2\n"
            "G1 Z100.0 F1000\n"  # way above last tier
            "G1 X30 E3\n"
        )
        lines = _lines(gcode)
        tiers = compute_temp_tiers(220, 10, 1)  # single tier: z=1-11
        result = insert_temperatures(lines, tiers)
        texts = _raw_texts(result)

        m104_lines = [t for t in texts if t.startswith("M104")]
        # Only one M104 for the single tier
        assert len(m104_lines) == 1
        assert "S220" in m104_lines[0]
