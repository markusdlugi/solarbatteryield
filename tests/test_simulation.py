"""
Tests for the simulation module.

The simulation module is the core of the PV analysis application. It runs hourly
simulations of PV systems with optional battery storage, handling different coupling
types (AC/DC), inverter efficiency, load profiles, and seasonal variations.
"""
import pytest
import numpy as np

from solarbatteryield.models import SimulationParams
from solarbatteryield.simulation import simulate
from solarbatteryield.inverter_efficiency import INVERTER_EFFICIENCY_CURVES, DEFAULT_INVERTER_EFFICIENCY_CURVE


def _create_base_params(**overrides) -> SimulationParams:
    """Create base simulation parameters with sensible defaults."""
    defaults = dict(
        batt_loss_pct=10,
        dc_coupled=True,
        min_soc_summer_pct=10,
        min_soc_winter_pct=20,
        max_soc_summer_pct=100,
        max_soc_winter_pct=100,
        data_year=2015,
        inverter_limit_kw=0.8,
        inverter_efficiency_curve=INVERTER_EFFICIENCY_CURVES["median"],
        batt_inverter_efficiency_curve=INVERTER_EFFICIENCY_CURVES["median"],
        profile_mode="Erweitert",
        annual_kwh=3000,
        profile_base=[200] * 24,  # Constant 200W load
        profile_saturday=None,
        profile_sunday=None,
        yearly_profile=None,
        seasonal_enabled=False,
        season_winter_pct=100,
        season_summer_pct=100,
        flex_load_enabled=False,
        flex_min_yield=5.0,
        flex_pool_size=3,
        flex_delta=[0] * 24,
        flex_refresh_rate=0.5,
        periodic_load_enabled=False,
        periodic_delta=[0] * 24,
        periodic_interval_days=3,
    )
    defaults.update(overrides)
    return SimulationParams(**defaults)


def _create_constant_pv(power_kw: float, hours: int = 8760) -> np.ndarray:
    """Create constant PV generation array."""
    return np.full(hours, power_kw)


def _create_daytime_pv(peak_kw: float = 1.0, hours: int = 8760) -> np.ndarray:
    """Create PV array with generation only during daytime hours (6-18)."""
    pv = np.zeros(hours)
    for i in range(hours):
        hour = i % 24
        if 6 <= hour < 18:
            pv[i] = peak_kw
    return pv


class TestSimulationEnergyBalance:
    """Tests verifying energy conservation in simulations."""

    def test_should_balance_supply_and_consumption(self):
        """Should have total supply equal to total consumption."""
        # given
        params = _create_base_params()
        pv_data = _create_daytime_pv(peak_kw=0.5)

        # when
        result = simulate(pv_data, cap_gross=5.0, params=params)

        # then
        monthly = result.monthly
        total_direct_pv = sum(m.direct_pv for m in monthly.values())
        total_battery = sum(m.battery for m in monthly.values())
        total_grid = sum(m.grid_import for m in monthly.values())
        total_consumption = sum(m.consumption for m in monthly.values())
        supply = total_direct_pv + total_battery + total_grid
        assert supply == pytest.approx(total_consumption, rel=0.001)

    def test_should_track_total_consumption_correctly(self):
        """Should track total consumption matching the load profile."""
        # given
        constant_load_watts = 300
        params = _create_base_params(profile_base=[constant_load_watts] * 24)
        pv_data = np.zeros(8760)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        expected_consumption = constant_load_watts / 1000 * 8760
        assert result.total_consumption == pytest.approx(expected_consumption, rel=0.01)


class TestSimulationWithoutBattery:
    """Tests for simulation behavior without battery storage."""

    def test_should_import_all_consumption_without_pv(self):
        """Should import all energy from grid when there is no PV generation."""
        # given
        params = _create_base_params()
        pv_data = np.zeros(8760)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        assert result.grid_import == pytest.approx(result.total_consumption, rel=0.01)
        assert result.feed_in == pytest.approx(0.0, abs=0.1)

    def test_should_feed_in_excess_pv_without_battery(self):
        """Should feed excess PV to grid when no battery is available."""
        # given
        params = _create_base_params(
            profile_base=[100] * 24,  # Low load: 100W
            inverter_limit_kw=None,   # No inverter limit
        )
        pv_data = _create_constant_pv(power_kw=1.0)  # 1kW constant

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        assert result.feed_in > 0
        assert result.grid_import > 0  # Still need grid at night due to load regression

    def test_should_use_direct_pv_before_grid(self):
        """Should prioritize direct PV consumption over grid import."""
        # given
        params = _create_base_params(
            profile_base=[500] * 24,  # 500W load
        )
        pv_data = _create_daytime_pv(peak_kw=0.3)  # 300W during day

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        total_direct_pv = sum(m.direct_pv for m in result.monthly.values())
        assert total_direct_pv > 0
        assert result.grid_import < result.total_consumption


class TestSimulationWithBattery:
    """Tests for simulation behavior with battery storage."""

    def test_should_reduce_grid_import_with_battery(self):
        """Should reduce grid import when battery stores daytime surplus."""
        # given
        params = _create_base_params(profile_base=[200] * 24)
        pv_data = _create_daytime_pv(peak_kw=0.8)

        # when
        result_no_battery = simulate(pv_data, cap_gross=0.0, params=params)
        result_with_battery = simulate(pv_data, cap_gross=5.0, params=params)

        # then
        assert result_with_battery.grid_import < result_no_battery.grid_import

    def test_should_reduce_feed_in_with_battery(self):
        """Should reduce feed-in when battery absorbs surplus."""
        # given
        params = _create_base_params(
            profile_base=[100] * 24,
            inverter_limit_kw=None,
        )
        pv_data = _create_daytime_pv(peak_kw=1.0)

        # when
        result_no_battery = simulate(pv_data, cap_gross=0.0, params=params)
        result_with_battery = simulate(pv_data, cap_gross=5.0, params=params)

        # then
        assert result_with_battery.feed_in < result_no_battery.feed_in

    def test_should_count_battery_cycles(self):
        """Should track battery full cycles correctly."""
        # given
        params = _create_base_params(profile_base=[300] * 24)
        pv_data = _create_daytime_pv(peak_kw=1.0)
        battery_capacity = 2.0

        # when
        result = simulate(pv_data, cap_gross=battery_capacity, params=params)

        # then
        assert result.full_cycles > 0

    def test_should_return_zero_cycles_without_battery(self):
        """Should return zero full cycles when no battery is present."""
        # given
        params = _create_base_params()
        pv_data = _create_daytime_pv(peak_kw=1.0)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        assert result.full_cycles == pytest.approx(0.0)

    def test_should_respect_min_soc_limit(self):
        """Should not discharge battery below minimum SoC."""
        # given
        params = _create_base_params(
            min_soc_summer_pct=50,
            min_soc_winter_pct=50,
            profile_base=[500] * 24,  # High load to drain battery
        )
        # Very limited PV - only enough to charge partially
        pv_data = _create_daytime_pv(peak_kw=0.2)
        battery_capacity = 2.0

        # when
        result = simulate(pv_data, cap_gross=battery_capacity, params=params)

        # then
        # With 50% min SoC, only half the battery is usable
        # Grid import should be higher than with no min SoC limit
        params_no_min = _create_base_params(
            min_soc_summer_pct=0,
            min_soc_winter_pct=0,
            profile_base=[500] * 24,
        )
        result_no_min = simulate(pv_data, cap_gross=battery_capacity, params=params_no_min)
        assert result.grid_import >= result_no_min.grid_import


class TestInverterLimit:
    """Tests for inverter limit behavior."""

    def test_should_curtail_when_exceeding_inverter_limit(self):
        """Should curtail PV generation that exceeds inverter capacity."""
        # given
        params = _create_base_params(
            inverter_limit_kw=0.5,  # 500W limit
            profile_base=[0] * 24,  # No load
        )
        pv_data = _create_constant_pv(power_kw=1.0)  # 1kW generation

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        assert result.curtailed > 0

    def test_should_not_curtail_within_inverter_limit(self):
        """Should not curtail when PV is within inverter capacity."""
        # given
        params = _create_base_params(
            inverter_limit_kw=2.0,  # 2kW limit
            profile_base=[0] * 24,
        )
        pv_data = _create_constant_pv(power_kw=0.5)  # 500W generation

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        assert result.curtailed == pytest.approx(0.0, abs=0.1)

    def test_should_not_curtail_without_inverter_limit(self):
        """Should not curtail when inverter limit is disabled."""
        # given
        params = _create_base_params(
            inverter_limit_kw=None,
            profile_base=[0] * 24,
        )
        pv_data = _create_constant_pv(power_kw=5.0)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        assert result.curtailed == pytest.approx(0.0, abs=0.1)


class TestDcVsAcCoupling:
    """Tests comparing DC-coupled and AC-coupled battery systems."""

    def test_should_have_higher_feed_in_with_dc_coupling(self):
        """Should have higher feed-in with DC coupling due to more efficient battery charging."""
        # given
        params_dc = _create_base_params(dc_coupled=True, profile_base=[300] * 24)
        params_ac = _create_base_params(dc_coupled=False, profile_base=[300] * 24)
        pv_data = _create_daytime_pv(peak_kw=0.8)
        battery_capacity = 3.0

        # when
        result_dc = simulate(pv_data, cap_gross=battery_capacity, params=params_dc)
        result_ac = simulate(pv_data, cap_gross=battery_capacity, params=params_ac)

        # then
        # DC-coupled charges battery more efficiently (no AC->DC conversion loss)
        # This means the battery fills with less energy input, leaving more surplus for feed-in
        # AC-coupled has additional conversion loss when charging, so more of the surplus
        # is "consumed" by the charging process, resulting in less feed-in
        assert result_dc.feed_in > result_ac.feed_in

    def test_should_have_lower_grid_import_with_dc_coupling(self):
        """Should have lower grid import with DC coupling due to more efficient storage."""
        # given
        # Use a scenario where battery doesn't always fill completely
        # so DC's more efficient charging results in more stored energy
        params_dc = _create_base_params(dc_coupled=True, profile_base=[400] * 24)
        params_ac = _create_base_params(dc_coupled=False, profile_base=[400] * 24)
        # Moderate PV that won't always fill the battery
        pv_data = _create_daytime_pv(peak_kw=0.6)
        battery_capacity = 5.0

        # when
        result_dc = simulate(pv_data, cap_gross=battery_capacity, params=params_dc)
        result_ac = simulate(pv_data, cap_gross=battery_capacity, params=params_ac)

        # then
        # DC-coupled stores more energy (no AC->DC conversion loss when charging)
        # This means more energy is available for evening discharge, reducing grid import
        assert result_dc.grid_import < result_ac.grid_import


class TestSeasonalSocLimits:
    """Tests for seasonal SoC limit behavior."""

    def test_should_apply_winter_soc_limits_in_winter(self):
        """Should use winter SoC limits during winter months."""
        # given
        # Create PV data for just January (winter)
        hours_january = 31 * 24
        pv_data = _create_daytime_pv(peak_kw=0.5, hours=hours_january)
        
        params_different_limits = _create_base_params(
            min_soc_summer_pct=10,
            min_soc_winter_pct=50,  # Higher minimum in winter
            profile_base=[500] * 24,
        )
        params_same_limits = _create_base_params(
            min_soc_summer_pct=10,
            min_soc_winter_pct=10,
            profile_base=[500] * 24,
        )

        # when
        result_different = simulate(pv_data, cap_gross=3.0, params=params_different_limits)
        result_same = simulate(pv_data, cap_gross=3.0, params=params_same_limits)

        # then
        # With higher winter min SoC, less battery can be used -> more grid import
        assert result_different.grid_import > result_same.grid_import


class TestMonthlyTracking:
    """Tests for monthly energy tracking."""

    def test_should_track_all_twelve_months(self):
        """Should have data for all 12 months."""
        # given
        params = _create_base_params()
        pv_data = _create_daytime_pv()

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        assert len(result.monthly) == 12
        assert all(month in result.monthly for month in range(1, 13))

    def test_should_sum_monthly_to_total(self):
        """Should have monthly values summing to annual totals."""
        # given
        params = _create_base_params()
        pv_data = _create_daytime_pv(peak_kw=0.5)

        # when
        result = simulate(pv_data, cap_gross=2.0, params=params)

        # then
        monthly_consumption = sum(m.consumption for m in result.monthly.values())
        monthly_grid_import = sum(m.grid_import for m in result.monthly.values())
        monthly_feed_in = sum(m.feed_in for m in result.monthly.values())
        
        assert monthly_consumption == pytest.approx(result.total_consumption, rel=0.001)
        assert monthly_grid_import == pytest.approx(result.grid_import, rel=0.001)
        assert monthly_feed_in == pytest.approx(result.feed_in, rel=0.001)


class TestBatteryLosses:
    """Tests for battery efficiency/loss handling."""

    def test_should_apply_battery_losses(self):
        """Should reduce effective battery capacity due to charge/discharge losses."""
        # given
        params_high_loss = _create_base_params(batt_loss_pct=20, profile_base=[300] * 24)
        params_low_loss = _create_base_params(batt_loss_pct=5, profile_base=[300] * 24)
        pv_data = _create_daytime_pv(peak_kw=0.8)

        # when
        result_high_loss = simulate(pv_data, cap_gross=3.0, params=params_high_loss)
        result_low_loss = simulate(pv_data, cap_gross=3.0, params=params_low_loss)

        # then
        # Higher losses should result in more grid import
        assert result_high_loss.grid_import > result_low_loss.grid_import


class TestFlexibleLoad:
    """Tests for flexible load shifting functionality."""

    def test_should_add_flex_load_on_sunny_days(self):
        """Should add flexible load when PV yield exceeds threshold."""
        # given
        flex_delta = [0] * 24
        flex_delta[12] = 500  # Add 500W at noon
        
        params_flex = _create_base_params(
            flex_load_enabled=True,
            flex_min_yield=1.0,  # Low threshold
            flex_pool_size=365,
            flex_delta=flex_delta,
            profile_base=[200] * 24,
        )
        params_no_flex = _create_base_params(
            flex_load_enabled=False,
            profile_base=[200] * 24,
        )
        # High PV to trigger flex
        pv_data = _create_daytime_pv(peak_kw=1.0)

        # when
        result_flex = simulate(pv_data, cap_gross=0.0, params=params_flex)
        result_no_flex = simulate(pv_data, cap_gross=0.0, params=params_no_flex)

        # then
        assert result_flex.total_consumption > result_no_flex.total_consumption

    def test_should_not_add_flex_load_on_cloudy_days(self):
        """Should not add flexible load when PV yield is below threshold."""
        # given
        flex_delta = [0] * 24
        flex_delta[12] = 500
        
        params = _create_base_params(
            flex_load_enabled=True,
            flex_min_yield=100.0,  # Very high threshold - never reached
            flex_pool_size=365,
            flex_delta=flex_delta,
            profile_base=[200] * 24,
        )
        pv_data = _create_daytime_pv(peak_kw=0.1)  # Very low PV

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        # Consumption should match base profile (no flex added)
        base_consumption = 200 / 1000 * 8760
        assert result.total_consumption == pytest.approx(base_consumption, rel=0.01)

    def test_should_limit_consecutive_flex_days_to_pool_size(self):
        """Should not exceed pool_size consecutive flex days."""
        # given
        flex_delta = [500] * 24  # Add 500W all day
        pool_size = 3
        
        params = _create_base_params(
            flex_load_enabled=True,
            flex_min_yield=0.1,  # Very low threshold - always triggers if pool available
            flex_pool_size=pool_size,
            flex_refresh_rate=0.0,  # No refresh - pool depletes completely
            flex_delta=flex_delta,
            profile_base=[200] * 24,
        )
        # PV for 10 consecutive sunny days (enough to deplete pool)
        hours_10_days = 10 * 24
        pv_data = _create_daytime_pv(peak_kw=1.0, hours=hours_10_days)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        # Only pool_size days should have flex load added
        base_consumption = 200 / 1000 * hours_10_days
        flex_consumption = 500 / 1000 * 24 * pool_size
        expected = base_consumption + flex_consumption
        assert result.total_consumption == pytest.approx(expected, rel=0.01)

    def test_should_refresh_pool_on_non_flex_days(self):
        """Should increase flex pool on days when flex is not used."""
        # given
        flex_delta = [500] * 24
        pool_size = 2
        refresh_rate = 1.0  # Fully refresh 1 use per non-flex day
        
        params = _create_base_params(
            flex_load_enabled=True,
            flex_min_yield=5.0,  # Moderate threshold
            flex_pool_size=pool_size,
            flex_refresh_rate=refresh_rate,
            flex_delta=flex_delta,
            profile_base=[200] * 24,
        )
        
        # Pattern: 2 sunny days (use pool), 2 cloudy days (refresh pool), 2 sunny days (use again)
        hours_6_days = 6 * 24
        pv_data = np.zeros(hours_6_days)
        # Day 0-1: sunny (above threshold)
        for h in range(2 * 24):
            if 6 <= h % 24 < 18:
                pv_data[h] = 1.0
        # Day 2-3: cloudy (no flex, pool refreshes)
        # Already zeros
        # Day 4-5: sunny again (should use refreshed pool)
        for h in range(4 * 24, 6 * 24):
            if 6 <= h % 24 < 18:
                pv_data[h] = 1.0

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        # Should have flex on days 0, 1, 4, 5 (4 days total, pool refreshed in between)
        base_consumption = 200 / 1000 * hours_6_days
        flex_consumption = 500 / 1000 * 24 * 4  # 4 flex days
        expected = base_consumption + flex_consumption
        assert result.total_consumption == pytest.approx(expected, rel=0.05)


class TestPeriodicLoad:
    """Tests for periodic load functionality."""

    def test_should_add_periodic_load_on_interval_days(self):
        """Should add periodic load on scheduled days."""
        # given
        periodic_delta = [0] * 24
        periodic_delta[0] = 1000  # Add 1kW at midnight
        
        params_periodic = _create_base_params(
            periodic_load_enabled=True,
            periodic_interval_days=1,  # Every day
            periodic_delta=periodic_delta,
            profile_base=[100] * 24,
        )
        params_no_periodic = _create_base_params(
            periodic_load_enabled=False,
            profile_base=[100] * 24,
        )
        pv_data = np.zeros(8760)

        # when
        result_periodic = simulate(pv_data, cap_gross=0.0, params=params_periodic)
        result_no_periodic = simulate(pv_data, cap_gross=0.0, params=params_no_periodic)

        # then
        assert result_periodic.total_consumption > result_no_periodic.total_consumption

    def test_should_respect_periodic_interval(self):
        """Should only add periodic load every N days."""
        # given
        periodic_delta = [1000] * 24  # Add 1kW all day
        
        params_every_day = _create_base_params(
            periodic_load_enabled=True,
            periodic_interval_days=1,
            periodic_delta=periodic_delta,
            profile_base=[100] * 24,
        )
        params_every_third = _create_base_params(
            periodic_load_enabled=True,
            periodic_interval_days=3,
            periodic_delta=periodic_delta,
            profile_base=[100] * 24,
        )
        pv_data = np.zeros(8760)

        # when
        result_every_day = simulate(pv_data, cap_gross=0.0, params=params_every_day)
        result_every_third = simulate(pv_data, cap_gross=0.0, params=params_every_third)

        # then
        # Every third day should have roughly 1/3 the additional consumption
        base_consumption = 100 / 1000 * 8760
        extra_every_day = result_every_day.total_consumption - base_consumption
        extra_every_third = result_every_third.total_consumption - base_consumption
        assert extra_every_third == pytest.approx(extra_every_day / 3, rel=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


