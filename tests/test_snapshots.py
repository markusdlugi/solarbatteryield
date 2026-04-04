"""
Snapshot tests for the simulation engine.

These tests use syrupy to pin exact simulation results for predefined scenarios.
They act as regression tests to detect any changes in simulation behavior,
whether intentional or accidental.

Unlike unit tests (which verify specific behaviors in isolation with simplified
inputs), these snapshot tests use realistic scenarios with:
- Synthetic PV data (~2 kWp system) with seasonal variation and daily bell curves
- Realistic household load profiles (~7 kWh/day)

The pinned values include monthly breakdowns of:
- direct_pv: Energy consumed directly from PV (kWh)
- battery: Energy discharged from battery (kWh)
- grid_import: Energy imported from grid (kWh)
- feed_in: Energy exported to grid (kWh)
- consumption: Total energy consumed (kWh)
- pv_generation: Total PV generation (kWh)

Usage:
    Run tests normally to compare against existing snapshots:
        pytest tests/test_snapshots.py -v
    
    Update snapshots after intentional changes:
        pytest tests/test_snapshots.py --snapshot-update
"""
import pytest
import numpy as np
from syrupy.assertion import SnapshotAssertion

from solarbatteryield.models import SimulationParams, SimulationResult
from solarbatteryield.simulation import simulate
from solarbatteryield.inverter_efficiency import INVERTER_EFFICIENCY_CURVES


def _result_to_snapshot_dict(result: SimulationResult) -> dict:
    """
    Convert SimulationResult to a dictionary suitable for snapshot comparison.
    
    Rounds values to 2 decimal places for readability and to avoid
    floating-point precision issues across different platforms.
    """
    def round_val(v: float) -> float:
        rounded = round(float(v), 2)
        # Avoid negative zero in output
        return 0.0 if rounded == 0.0 else rounded
    
    monthly_data = {}
    for month, data in result.monthly.items():
        monthly_data[month] = {
            "direct_pv": round_val(data.direct_pv),
            "battery": round_val(data.battery),
            "grid_import": round_val(data.grid_import),
            "feed_in": round_val(data.feed_in),
            "consumption": round_val(data.consumption),
            "pv_generation": round_val(data.pv_generation),
        }
    
    return {
        "totals": {
            "grid_import": round_val(result.grid_import),
            "total_consumption": round_val(result.total_consumption),
            "feed_in": round_val(result.feed_in),
            "curtailed": round_val(result.curtailed),
            "full_cycles": round_val(result.full_cycles),
        },
        "monthly": monthly_data,
    }


def _create_simulation_params(**overrides) -> SimulationParams:
    """Create simulation parameters with sensible defaults for snapshot tests."""
    defaults = dict(
        batt_loss_pct=10,
        dc_coupled=True,
        min_soc_summer_pct=10,
        min_soc_winter_pct=20,
        max_soc_summer_pct=100,
        max_soc_winter_pct=100,
        data_year=2015,
        inverter_limit_kw=None,  # No inverter limit by default for realistic scenarios
        inverter_efficiency_curve=INVERTER_EFFICIENCY_CURVES["median"],
        batt_inverter_efficiency_curve=INVERTER_EFFICIENCY_CURVES["median"],
        profile_mode="Erweitert",
        annual_kwh=3500,
        profile_base=[300] * 24,  # Constant 300W load
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


def _create_synthetic_pv_data(hours: int = 8760, peak_power_kw: float = 2.0) -> np.ndarray:
    """
    Create synthetic PV generation data that simulates realistic daily patterns.
    
    Generates a bell curve pattern for each day with:
    - Peak generation around noon (hour 12)
    - No generation at night
    - Seasonal variation (more in summer, less in winter)
    
    Args:
        hours: Number of hours to simulate (default: 8760 = 1 year)
        peak_power_kw: Peak power in kW at summer noon (default: 2.0 kW)
                      This represents a ~2.5 kWp system accounting for losses
    """
    pv_data = np.zeros(hours)
    
    for i in range(hours):
        hour = i % 24
        day = i // 24
        
        # Calculate day of year (1-365)
        day_of_year = day % 365 + 1
        
        # Seasonal factor: peaks in summer (day ~172), lowest in winter
        seasonal_factor = 0.5 + 0.5 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
        
        # Daily pattern: bell curve centered at noon
        if 5 <= hour <= 20:
            # Hours from solar noon (12)
            hours_from_noon = abs(hour - 12.5)
            # Gaussian-like curve
            daily_factor = np.exp(-0.3 * hours_from_noon ** 2)
            
            # Peak power scaled by season
            pv_data[i] = peak_power_kw * seasonal_factor * daily_factor
        else:
            pv_data[i] = 0.0
    
    return pv_data


def _create_realistic_load_profile() -> list[float]:
    """
    Create a realistic daily load profile in Watts.
    
    Pattern:
    - Low overnight (11pm-5am): ~150W base load
    - Morning peak (6am-9am): ~400W
    - Daytime moderate (9am-5pm): ~250W
    - Evening peak (5pm-10pm): ~500W
    """
    profile = [
        150, 150, 150, 150, 150, 150,  # 00:00-05:59: Night
        300, 400, 450, 300,            # 06:00-09:59: Morning
        250, 250, 300, 250, 250, 250,  # 10:00-15:59: Daytime
        350, 500, 550, 500, 450, 350,  # 16:00-21:59: Evening
        200, 150,                       # 22:00-23:59: Late evening
    ]
    return profile


class TestScenarioNoBattery:
    """Snapshot tests for simulation without battery storage."""

    @pytest.fixture(scope="class")
    def scenario_result(self) -> SimulationResult:
        """Run simulation without battery and return results."""
        params = _create_simulation_params(
            profile_base=_create_realistic_load_profile(),
        )
        pv_data = _create_synthetic_pv_data()
        return simulate(pv_data, cap_gross=0.0, params=params)

    def test_snapshot_no_battery_results(self, scenario_result, snapshot: SnapshotAssertion):
        """Should match snapshot for no-battery scenario with realistic load profile."""
        # when
        result_dict = _result_to_snapshot_dict(scenario_result)

        # then
        assert result_dict == snapshot


class TestScenarioWithBattery:
    """Snapshot tests for simulation with battery storage."""

    @pytest.fixture(scope="class")
    def scenario_results(self) -> dict[str, SimulationResult]:
        """Run simulations with different battery sizes."""
        params = _create_simulation_params(
            profile_base=_create_realistic_load_profile(),
        )
        pv_data = _create_synthetic_pv_data()
        
        return {
            "small_battery": simulate(pv_data, cap_gross=3.0, params=params),
            "large_battery": simulate(pv_data, cap_gross=10.0, params=params),
        }


    def test_snapshot_small_battery_results(self, scenario_results, snapshot: SnapshotAssertion):
        """Should match snapshot for 3kWh battery scenario."""
        # when
        result_dict = _result_to_snapshot_dict(scenario_results["small_battery"])

        # then
        assert result_dict == snapshot

    def test_snapshot_large_battery_results(self, scenario_results, snapshot: SnapshotAssertion):
        """Should match snapshot for 10kWh battery scenario."""
        # when
        result_dict = _result_to_snapshot_dict(scenario_results["large_battery"])

        # then
        assert result_dict == snapshot


class TestScenarioDcVsAcCoupling:
    """Snapshot tests comparing DC-coupled and AC-coupled systems."""

    @pytest.fixture(scope="class")
    def coupling_results(self) -> dict[str, SimulationResult]:
        """Run simulations with DC and AC coupling."""
        pv_data = _create_synthetic_pv_data()
        battery_capacity = 5.0
        
        params_dc = _create_simulation_params(
            dc_coupled=True,
            profile_base=_create_realistic_load_profile(),
        )
        params_ac = _create_simulation_params(
            dc_coupled=False,
            profile_base=_create_realistic_load_profile(),
        )
        
        return {
            "dc_coupled": simulate(pv_data, cap_gross=battery_capacity, params=params_dc),
            "ac_coupled": simulate(pv_data, cap_gross=battery_capacity, params=params_ac),
        }


    def test_snapshot_dc_coupled_results(self, coupling_results, snapshot: SnapshotAssertion):
        """Should match snapshot for DC-coupled scenario."""
        # when
        result_dict = _result_to_snapshot_dict(coupling_results["dc_coupled"])

        # then
        assert result_dict == snapshot

    def test_snapshot_ac_coupled_results(self, coupling_results, snapshot: SnapshotAssertion):
        """Should match snapshot for AC-coupled scenario."""
        # when
        result_dict = _result_to_snapshot_dict(coupling_results["ac_coupled"])

        # then
        assert result_dict == snapshot


class TestScenarioInverterLimit:
    """Snapshot tests for inverter limit behavior."""

    @pytest.fixture(scope="class")
    def inverter_results(self) -> dict[str, SimulationResult]:
        """Run simulations with and without inverter limit."""
        pv_data = _create_synthetic_pv_data()
        
        params_limited = _create_simulation_params(
            inverter_limit_kw=1.5,  # 1.5 kW limit with 2 kW peak PV
            profile_base=[100] * 24,  # Low load to maximize surplus
        )
        params_unlimited = _create_simulation_params(
            inverter_limit_kw=None,
            profile_base=[100] * 24,
        )
        
        return {
            "limited": simulate(pv_data, cap_gross=0.0, params=params_limited),
            "unlimited": simulate(pv_data, cap_gross=0.0, params=params_unlimited),
        }


    def test_snapshot_limited_inverter_results(self, inverter_results, snapshot: SnapshotAssertion):
        """Should match snapshot for limited inverter scenario."""
        # when
        result_dict = _result_to_snapshot_dict(inverter_results["limited"])

        # then
        assert result_dict == snapshot

    def test_snapshot_unlimited_inverter_results(self, inverter_results, snapshot: SnapshotAssertion):
        """Should match snapshot for unlimited inverter scenario."""
        # when
        result_dict = _result_to_snapshot_dict(inverter_results["unlimited"])

        # then
        assert result_dict == snapshot


class TestScenarioSeasonalBehavior:
    """Snapshot tests for seasonal variations with realistic PV pattern."""

    @pytest.fixture(scope="class")
    def seasonal_result(self) -> SimulationResult:
        """Run full year simulation and return results."""
        params = _create_simulation_params(
            profile_base=_create_realistic_load_profile(),
        )
        pv_data = _create_synthetic_pv_data()
        return simulate(pv_data, cap_gross=5.0, params=params)


    def test_snapshot_seasonal_results(self, seasonal_result, snapshot: SnapshotAssertion):
        """Should match snapshot for seasonal scenario with 5kWh battery."""
        # when
        result_dict = _result_to_snapshot_dict(seasonal_result)

        # then
        assert result_dict == snapshot



if __name__ == "__main__":
    pytest.main([__file__, "-v"])


