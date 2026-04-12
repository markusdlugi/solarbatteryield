"""
Unit tests for Battery class hierarchy.

Tests each Battery implementation in isolation (without the full simulate() loop)
to verify energy flow physics for a single hour.
"""
import pytest

from solarbatteryield.models import DischargeStrategyConfig, TimeWindow
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
        assert result.grid_import == pytest.approx(0.0, abs=0.02)

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


# ─── Base Load Strategy Tests ────────────────────────────────────────────────

_BASE_LOAD_CONFIG = DischargeStrategyConfig(mode="base_load", base_load_w=200)


def _make_dc_battery_with_strategy(
        cap: float = 5.0, batt_eff: float = 1.0, inv_cap: float = 10.0,
        strategy: DischargeStrategyConfig = _BASE_LOAD_CONFIG,
) -> DcCoupledBattery:
    """Create a DcCoupledBattery with strategy and full SoC range."""
    batt = DcCoupledBattery(
        cap_gross=cap, batt_eff=batt_eff, inv_cap=inv_cap,
        inv_eff_curve=_EFF, strategy_config=strategy,
    )
    batt.set_soc_limits(0.0, cap)
    return batt


def _make_ac_battery_with_strategy(
        cap: float = 5.0, batt_eff: float = 1.0, inv_cap: float = 10.0,
        strategy: DischargeStrategyConfig = _BASE_LOAD_CONFIG,
) -> AcCoupledBattery:
    """Create an AcCoupledBattery with strategy and full SoC range."""
    batt = AcCoupledBattery(
        cap_gross=cap, batt_eff=batt_eff, inv_cap=inv_cap,
        inv_eff_curve=_EFF, batt_inv_eff_curve=_EFF,
        strategy_config=strategy,
    )
    batt.set_soc_limits(0.0, cap)
    return batt


class TestBaseLoadDcCoupled:
    """Tests for base_load strategy with DC-coupled battery."""

    def test_should_not_discharge_when_pv_exceeds_target(self):
        """Should not discharge battery when PV alone can meet the target."""
        # given
        batt = _make_dc_battery_with_strategy()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge
        soc_before = batt.soc

        # when — PV (2 kW) >> target (0.2 kW)
        result = batt.process_hour(gen_dc=2.0, load=0.5, hour=13)

        # then
        assert batt.soc >= soc_before  # Battery charged (not discharged)
        assert result.battery_discharge == pytest.approx(0.0)

    def test_should_discharge_to_fill_gap_between_pv_and_target(self):
        """Should discharge battery to fill the gap when PV < target."""
        # given
        batt = _make_dc_battery_with_strategy()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge
        soc_after_charge = batt.soc

        # when — PV (0.0 kW) < target (0.2 kW), load = 0.5 kW
        result = batt.process_hour(gen_dc=0.0, load=0.5, hour=20)

        # then
        assert batt.soc < soc_after_charge
        assert result.battery_discharge > 0

    def test_should_never_exceed_target_output(self):
        """Battery + PV system output should not exceed target."""
        # given — target = 0.2 kW, PV = 0.1 kW, load = 0.5 kW
        batt = _make_dc_battery_with_strategy()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge

        # when
        result = batt.process_hour(gen_dc=0.1, load=0.5, hour=20)

        # then — direct_pv + battery_discharge ≤ target (0.2 kW) + tolerance
        system_output = result.direct_pv + result.battery_discharge
        assert system_output <= 0.2 + 0.02

    def test_should_feed_in_when_load_less_than_target(self):
        """Should have feed-in when system output exceeds load (blind output)."""
        # given — target = 0.2 kW, load = 0.05 kW
        batt = _make_dc_battery_with_strategy()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge

        # when
        result = batt.process_hour(gen_dc=0.0, load=0.05, hour=20)

        # then
        assert result.feed_in > 0

    def test_should_import_from_grid_when_battery_empty(self):
        """Should import from grid when battery is empty and PV < target."""
        # given — empty battery (no pre-charge)
        batt = _make_dc_battery_with_strategy()

        # when
        result = batt.process_hour(gen_dc=0.0, load=0.5, hour=20)

        # then
        assert result.grid_import > 0


class TestBaseLoadAcCoupled:
    """Tests for base_load strategy with AC-coupled battery."""

    def test_should_not_discharge_when_pv_exceeds_target(self):
        """Should not discharge battery when PV alone can meet the target."""
        # given
        batt = _make_ac_battery_with_strategy()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge
        soc_before = batt.soc

        # when
        result = batt.process_hour(gen_dc=2.0, load=0.5, hour=13)

        # then
        assert batt.soc >= soc_before
        assert result.battery_discharge == pytest.approx(0.0)

    def test_should_discharge_to_fill_gap_between_pv_and_target(self):
        """Should discharge battery to fill the gap when PV < target."""
        # given
        batt = _make_ac_battery_with_strategy()
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge
        soc_after_charge = batt.soc

        # when
        result = batt.process_hour(gen_dc=0.0, load=0.5, hour=20)

        # then
        assert batt.soc < soc_after_charge
        assert result.battery_discharge > 0


# ─── Time Window Strategy Tests ──────────────────────────────────────────────


class TestTimeWindowBattery:
    """Tests for time_window strategy with battery."""

    def test_should_discharge_only_during_active_windows(self):
        """Should discharge only when the current hour is in an active window."""
        # given
        windows = (TimeWindow(start_hour=17, end_hour=22, power_w=300),)
        strategy = DischargeStrategyConfig(mode="time_window", time_windows=windows)
        batt = _make_dc_battery_with_strategy(strategy=strategy)

        # Pre-charge
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)

        # when — outside window
        result_outside = batt.process_hour(gen_dc=0.0, load=0.5, hour=12)
        # when — inside window
        result_inside = batt.process_hour(gen_dc=0.0, load=0.5, hour=19)

        # then
        assert result_outside.battery_discharge == pytest.approx(0.0)
        assert result_inside.battery_discharge > 0

    def test_should_still_charge_during_inactive_windows(self):
        """Should charge battery from PV surplus even outside active windows."""
        # given
        windows = (TimeWindow(start_hour=17, end_hour=22, power_w=300),)
        strategy = DischargeStrategyConfig(mode="time_window", time_windows=windows)
        batt = _make_dc_battery_with_strategy(strategy=strategy)
        soc_initial = batt.soc

        # when — PV surplus at noon, outside discharge window
        batt.process_hour(gen_dc=2.0, load=0.1, hour=12)

        # then — battery should have charged
        assert batt.soc > soc_initial

    def test_should_use_different_powers_for_different_windows(self):
        """Should respect power settings of individual windows."""
        # given
        windows = (
            TimeWindow(start_hour=6, end_hour=10, power_w=100),
            TimeWindow(start_hour=17, end_hour=22, power_w=500),
        )
        strategy = DischargeStrategyConfig(mode="time_window", time_windows=windows)

        # Morning window battery
        batt_morning = _make_dc_battery_with_strategy(strategy=strategy)
        batt_morning.process_hour(gen_dc=5.0, load=0.1, hour=12)  # pre-charge

        # Evening window battery (identical starting state)
        batt_evening = _make_dc_battery_with_strategy(strategy=strategy)
        batt_evening.process_hour(gen_dc=5.0, load=0.1, hour=12)  # pre-charge

        # when
        result_morning = batt_morning.process_hour(gen_dc=0.0, load=1.0, hour=8)
        result_evening = batt_evening.process_hour(gen_dc=0.0, load=1.0, hour=19)

        # then — evening window has higher power → more discharge
        assert result_evening.battery_discharge > result_morning.battery_discharge


# ─── Battery-Full Surplus Optimization Tests ─────────────────────────────────


class TestBatteryFullSurplusOptimization:
    """Tests for PV surplus serving load when battery is full (target-based paths)."""

    def test_dc_should_reduce_grid_import_when_battery_full_and_surplus(self):
        """DC: When battery is full and PV > target, surplus should reduce grid import."""
        # given — battery at max SoC, PV >> target (200W), load > target
        strategy = DischargeStrategyConfig(mode="base_load", base_load_w=200)
        batt = _make_dc_battery_with_strategy(cap=2.0, strategy=strategy)
        batt.set_soc_limits(0.0, 2.0)
        # Fill battery completely
        batt.process_hour(gen_dc=5.0, load=0.0, hour=10)
        batt.process_hour(gen_dc=5.0, load=0.0, hour=11)
        assert batt.soc >= 1.9  # Battery nearly full

        # when — PV=1.0 kW (>> target 0.2 kW), load=0.5 kW
        result = batt.process_hour(gen_dc=1.0, load=0.5, hour=12)

        # then — surplus PV should partially serve remaining load
        # Without optimization: grid_import ≈ load - (regression on 0.2kW system output)
        # With optimization: grid_import is lower because surplus PV also serves load
        assert result.grid_import < 0.4  # Should be noticeably less than load
        assert result.direct_pv > 0.15  # More than just target's PV share

    def test_ac_should_reduce_grid_import_when_battery_full_and_surplus(self):
        """AC: When battery is full and PV > target, surplus should reduce grid import."""
        # given
        strategy = DischargeStrategyConfig(mode="base_load", base_load_w=200)
        batt = _make_ac_battery_with_strategy(cap=2.0, strategy=strategy)
        batt.set_soc_limits(0.0, 2.0)
        batt.process_hour(gen_dc=5.0, load=0.0, hour=10)
        batt.process_hour(gen_dc=5.0, load=0.0, hour=11)
        assert batt.soc >= 1.9

        # when
        result = batt.process_hour(gen_dc=1.0, load=0.5, hour=12)

        # then
        assert result.grid_import < 0.4
        assert result.direct_pv > 0.15

    def test_should_not_affect_surplus_when_battery_not_full(self):
        """When battery is NOT full, all surplus charges battery (no second regression)."""
        # given — battery empty, PV >> target
        strategy = DischargeStrategyConfig(mode="base_load", base_load_w=200)
        batt = _make_dc_battery_with_strategy(cap=10.0, strategy=strategy)
        batt.set_soc_limits(0.0, 10.0)
        soc_before = batt.soc

        # when — PV=2.0 kW, load=0.5 kW
        result = batt.process_hour(gen_dc=2.0, load=0.5, hour=12)

        # then — surplus charges battery, feed_in is minimal
        assert batt.soc > soc_before  # Battery charged from surplus
        assert result.feed_in < 0.05  # Nearly all surplus absorbed

    def test_should_export_all_surplus_when_no_load(self):
        """When load=0 and battery full, all surplus should be exported."""
        # given — battery full, no load
        strategy = DischargeStrategyConfig(mode="base_load", base_load_w=200)
        batt = _make_dc_battery_with_strategy(cap=2.0, strategy=strategy)
        batt.set_soc_limits(0.0, 2.0)
        batt.process_hour(gen_dc=5.0, load=0.0, hour=10)
        batt.process_hour(gen_dc=5.0, load=0.0, hour=11)

        # when — PV=1.0 kW, load=0.0
        result = batt.process_hour(gen_dc=1.0, load=0.0, hour=12)

        # then
        assert result.grid_import == pytest.approx(0.0)
        assert result.feed_in > 0

    def test_should_maintain_energy_balance_with_surplus_optimization(self):
        """Energy balance must hold: direct_pv + battery + grid = consumption."""
        # given — battery full, PV > target, load > target
        strategy = DischargeStrategyConfig(mode="base_load", base_load_w=200)
        for Factory in [_make_dc_battery_with_strategy, _make_ac_battery_with_strategy]:
            batt = Factory(cap=2.0, strategy=strategy)
            batt.set_soc_limits(0.0, 2.0)
            batt.process_hour(gen_dc=5.0, load=0.0, hour=10)
            batt.process_hour(gen_dc=5.0, load=0.0, hour=11)

            # when
            result = batt.process_hour(gen_dc=1.0, load=0.5, hour=12)

            # then
            supply = result.direct_pv + result.battery_discharge + result.grid_import
            assert supply == pytest.approx(result.consumption, rel=0.01)


# ─── Strategy Energy Balance Tests ───────────────────────────────────────────


class TestStrategyEnergyBalance:
    """Tests verifying energy conservation with non-default strategies."""

    @pytest.mark.parametrize("strategy_config", [
        DischargeStrategyConfig(mode="base_load", base_load_w=200),
        DischargeStrategyConfig(mode="base_load", base_load_w=500),
        DischargeStrategyConfig(
            mode="time_window",
            time_windows=(TimeWindow(start_hour=17, end_hour=22, power_w=300),),
        ),
    ])
    @pytest.mark.parametrize("BatteryFactory,extra_kwargs", [
        (_make_dc_battery_with_strategy, {}),
        (_make_ac_battery_with_strategy, {}),
    ])
    def test_should_balance_supply_and_consumption(self, strategy_config,
                                                   BatteryFactory, extra_kwargs):
        """Supply should equal consumption for all strategy configurations."""
        # given
        batt = BatteryFactory(strategy=strategy_config, **extra_kwargs)
        batt.process_hour(gen_dc=3.0, load=0.1, hour=12)  # pre-charge

        # when
        result = batt.process_hour(gen_dc=0.3, load=0.4, hour=19)

        # then
        supply = result.direct_pv + result.battery_discharge + result.grid_import
        assert supply == pytest.approx(result.consumption, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
