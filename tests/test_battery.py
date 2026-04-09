"""
Unit tests for Battery class hierarchy.

Tests each Battery implementation in isolation (without the full simulate() loop)
to verify energy flow physics for a single hour.
"""
import pytest

from solarbatteryield.simulation.battery import (
    NoBattery,
    DcCoupledBattery,
    AcCoupledBattery,
    create_battery,
)
from solarbatteryield.simulation.inverter_efficiency import (
    DEFAULT_INVERTER_EFFICIENCY_CURVE,
)

_EFF = DEFAULT_INVERTER_EFFICIENCY_CURVE


# ─── Factory Tests ───────────────────────────────────────────────────────────


class TestCreateBattery:
    """Tests for the create_battery factory function."""

    def test_should_return_no_battery_when_capacity_is_zero(self):
        """Should return NoBattery when cap_gross == 0."""
        # given
        cap_gross = 0.0

        # when
        battery = create_battery(
            cap_gross=cap_gross, batt_eff=0.9, inv_cap=0.8,
            inv_eff_curve=_EFF, dc_coupled=True,
        )

        # then
        assert isinstance(battery, NoBattery)

    def test_should_return_no_battery_when_capacity_is_negative(self):
        """Should return NoBattery when cap_gross < 0."""
        # given
        cap_gross = -1.0

        # when
        battery = create_battery(
            cap_gross=cap_gross, batt_eff=0.9, inv_cap=0.8,
            inv_eff_curve=_EFF, dc_coupled=True,
        )

        # then
        assert isinstance(battery, NoBattery)

    def test_should_return_dc_coupled_battery(self):
        """Should return DcCoupledBattery when dc_coupled=True and cap > 0."""
        # given/when
        battery = create_battery(
            cap_gross=5.0, batt_eff=0.9, inv_cap=0.8,
            inv_eff_curve=_EFF, dc_coupled=True,
        )

        # then
        assert isinstance(battery, DcCoupledBattery)

    def test_should_return_ac_coupled_battery(self):
        """Should return AcCoupledBattery when dc_coupled=False and cap > 0."""
        # given/when
        battery = create_battery(
            cap_gross=5.0, batt_eff=0.9, inv_cap=0.8,
            inv_eff_curve=_EFF, dc_coupled=False,
        )

        # then
        assert isinstance(battery, AcCoupledBattery)


# ─── NoBattery Tests ─────────────────────────────────────────────────────────


def _make_no_battery(inv_cap: float = 10.0) -> NoBattery:
    """Create a NoBattery instance with sensible defaults."""
    return NoBattery(cap_gross=0.0, batt_eff=1.0, inv_cap=inv_cap, inv_eff_curve=_EFF)


class TestNoBattery:
    """Tests for NoBattery (PV-only system)."""

    def test_should_have_zero_soc(self):
        """Should report 0 kWh / 0% SoC since there is no storage."""
        # given
        batt = _make_no_battery()

        # when/then
        assert batt.soc == 0.0
        assert batt.soc_pct == 0.0

    def test_should_have_zero_total_discharge_after_processing(self):
        """Should accumulate zero discharge even after processing hours."""
        # given
        batt = _make_no_battery()

        # when
        batt.process_hour(gen_dc=1.0, load=0.5, hour=12)

        # then
        assert batt.total_discharge == 0.0

    def test_should_report_zero_battery_discharge_in_result(self):
        """Should always return battery_discharge=0 in the hourly result."""
        # given
        batt = _make_no_battery()

        # when
        result = batt.process_hour(gen_dc=1.0, load=0.5, hour=12)

        # then
        assert result.battery_discharge == 0.0

    def test_should_feed_in_excess_pv(self):
        """Should feed in surplus when PV generation exceeds load."""
        # given
        batt = _make_no_battery()

        # when
        result = batt.process_hour(gen_dc=1.0, load=0.1, hour=12)

        # then
        assert result.feed_in > 0
        assert result.grid_import == pytest.approx(0.0, abs=0.01)

    def test_should_import_all_load_from_grid_when_no_pv(self):
        """Should import entire load from grid when there is no PV generation."""
        # given
        batt = _make_no_battery()

        # when
        result = batt.process_hour(gen_dc=0.0, load=0.5, hour=12)

        # then
        assert result.grid_import == pytest.approx(0.5)
        assert result.feed_in == pytest.approx(0.0)

    def test_should_curtail_pv_above_inverter_limit(self):
        """Should curtail PV generation that exceeds inverter capacity."""
        # given
        batt = _make_no_battery(inv_cap=0.5)  # 500W limit

        # when
        result = batt.process_hour(gen_dc=1.0, load=0.0, hour=12)

        # then
        assert result.curtailed > 0


# ─── DcCoupledBattery Tests ──────────────────────────────────────────────────


def _make_dc_battery(cap: float = 5.0, batt_eff: float = 1.0,
                     inv_cap: float = 10.0) -> DcCoupledBattery:
    """Create a DcCoupledBattery with SoC limits set to full range."""
    batt = DcCoupledBattery(cap_gross=cap, batt_eff=batt_eff, inv_cap=inv_cap, inv_eff_curve=_EFF)
    batt.set_soc_limits(0.0, cap)
    return batt


class TestDcCoupledBattery:
    """Tests for DcCoupledBattery."""

    def test_should_charge_battery_from_pv_surplus(self):
        """Should increase SoC when PV generation exceeds load."""
        # given
        batt = _make_dc_battery()

        # when
        batt.process_hour(gen_dc=2.0, load=0.5, hour=12)

        # then
        assert batt.soc > 0

    def test_should_discharge_battery_to_cover_deficit(self):
        """Should decrease SoC and report battery discharge when load exceeds PV."""
        # given
        batt = _make_dc_battery()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge
        soc_after_charge = batt.soc

        # when
        result = batt.process_hour(gen_dc=0.0, load=0.5, hour=20)

        # then
        assert batt.soc < soc_after_charge
        assert result.battery_discharge > 0

    def test_should_not_discharge_below_min_soc(self):
        """Should stop discharging at min SoC even with high load."""
        # given
        batt = _make_dc_battery(cap=2.0, batt_eff=1.0)
        batt.set_soc_limits(1.0, 2.0)  # min 50%
        batt.process_hour(gen_dc=2.0, load=0.1, hour=12)  # pre-charge

        # when
        batt.process_hour(gen_dc=0.0, load=5.0, hour=20)

        # then
        assert batt.soc >= 1.0 - 0.001  # float tolerance

    def test_should_not_charge_above_max_soc(self):
        """Should stop charging at max SoC even with large PV surplus."""
        # given
        batt = _make_dc_battery(cap=2.0, batt_eff=1.0)
        batt.set_soc_limits(0.0, 1.0)  # max 50%

        # when
        batt.process_hour(gen_dc=5.0, load=0.0, hour=12)

        # then
        assert batt.soc <= 1.0 + 0.001

    def test_should_accumulate_total_discharge_across_hours(self):
        """Should track cumulative discharge energy over multiple hours."""
        # given
        batt = _make_dc_battery()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge

        # when
        batt.process_hour(gen_dc=0.0, load=0.5, hour=20)
        batt.process_hour(gen_dc=0.0, load=0.5, hour=21)

        # then
        assert batt.total_discharge > 0


# ─── AcCoupledBattery Tests ──────────────────────────────────────────────────


def _make_ac_battery(cap: float = 5.0, batt_eff: float = 1.0,
                     inv_cap: float = 10.0) -> AcCoupledBattery:
    """Create an AcCoupledBattery with SoC limits set to full range."""
    batt = AcCoupledBattery(
        cap_gross=cap, batt_eff=batt_eff, inv_cap=inv_cap,
        inv_eff_curve=_EFF, batt_inv_eff_curve=_EFF,
    )
    batt.set_soc_limits(0.0, cap)
    return batt


class TestAcCoupledBattery:
    """Tests for AcCoupledBattery."""

    def test_should_charge_battery_from_pv_surplus(self):
        """Should increase SoC when PV generation exceeds load."""
        # given
        batt = _make_ac_battery()

        # when
        batt.process_hour(gen_dc=2.0, load=0.5, hour=12)

        # then
        assert batt.soc > 0

    def test_should_discharge_battery_to_cover_deficit(self):
        """Should decrease SoC and report battery discharge when load exceeds PV."""
        # given
        batt = _make_ac_battery()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge
        soc_after_charge = batt.soc

        # when
        result = batt.process_hour(gen_dc=0.0, load=0.5, hour=20)

        # then
        assert batt.soc < soc_after_charge
        assert result.battery_discharge > 0

    def test_should_not_discharge_below_min_soc(self):
        """Should stop discharging at min SoC even with high load."""
        # given
        batt = _make_ac_battery(cap=2.0, batt_eff=1.0)
        batt.set_soc_limits(1.0, 2.0)
        batt.process_hour(gen_dc=2.0, load=0.1, hour=12)  # pre-charge

        # when
        batt.process_hour(gen_dc=0.0, load=5.0, hour=20)

        # then
        assert batt.soc >= 1.0 - 0.001

    def test_should_not_charge_above_max_soc(self):
        """Should stop charging at max SoC even with large PV surplus."""
        # given
        batt = _make_ac_battery(cap=2.0, batt_eff=1.0)
        batt.set_soc_limits(0.0, 1.0)

        # when
        batt.process_hour(gen_dc=5.0, load=0.0, hour=12)

        # then
        assert batt.soc <= 1.0 + 0.001

    def test_should_accumulate_total_discharge_across_hours(self):
        """Should track cumulative discharge energy over multiple hours."""
        # given
        batt = _make_ac_battery()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge

        # when
        batt.process_hour(gen_dc=0.0, load=0.5, hour=20)
        batt.process_hour(gen_dc=0.0, load=0.5, hour=21)

        # then
        assert batt.total_discharge > 0


# ─── Energy Balance Tests ────────────────────────────────────────────────────


class TestBatteryEnergyBalance:
    """Tests verifying energy conservation in individual battery hours."""

    @pytest.mark.parametrize("BatteryClass,kwargs", [
        (NoBattery, {"cap_gross": 0, "batt_eff": 1.0, "inv_cap": 10.0}),
        (DcCoupledBattery, {"cap_gross": 5.0, "batt_eff": 0.9, "inv_cap": 10.0}),
        (AcCoupledBattery, {"cap_gross": 5.0, "batt_eff": 0.9, "inv_cap": 10.0,
                            "batt_inv_eff_curve": _EFF}),
    ])
    def test_should_balance_supply_and_consumption(self, BatteryClass, kwargs):
        """Supply (direct_pv + battery + grid) should equal consumption."""
        # given
        batt = BatteryClass(inv_eff_curve=_EFF, **kwargs)
        batt.set_soc_limits(0.0, kwargs.get("cap_gross", 0.0))
        if kwargs.get("cap_gross", 0) > 0:
            batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge

        # when
        result = batt.process_hour(gen_dc=0.5, load=0.4, hour=14)

        # then
        supply = result.direct_pv + result.battery_discharge + result.grid_import
        assert supply == pytest.approx(result.consumption, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
