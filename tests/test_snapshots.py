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
from syrupy.assertion import SnapshotAssertion

from conftest import (
    create_simulation_params,
    create_synthetic_pv_data,
    create_realistic_load_profile,
)
from solarbatteryield.models import (
    SimulationInput, SimulationResult, DischargeStrategyConfig, TimeWindow,
)
from solarbatteryield.simulation import simulate


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


def _create_snapshot_params(**overrides) -> SimulationInput:
    """Create simulation parameters for snapshot tests with sensible defaults."""
    # Set snapshot-specific defaults, but allow overrides to take precedence
    snapshot_defaults = {
        "inverter_limit_kw": None,  # No inverter limit by default for realistic scenarios
        "annual_kwh": 3500,
        "active_base": [300] * 24,  # Constant 300W load
    }
    # Merge: overrides take precedence over snapshot_defaults
    merged = {**snapshot_defaults, **overrides}
    return create_simulation_params(**merged)


class TestScenarioNoBattery:
    """Snapshot tests for simulation without battery storage."""

    @pytest.fixture(scope="class")
    def scenario_result(self) -> SimulationResult:
        """Run simulation without battery and return results."""
        params = _create_snapshot_params(
            active_base=create_realistic_load_profile(),
        )
        pv_data = create_synthetic_pv_data()
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
        params = _create_snapshot_params(
            active_base=create_realistic_load_profile(),
        )
        pv_data = create_synthetic_pv_data()

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
        pv_data = create_synthetic_pv_data()
        battery_capacity = 5.0

        params_dc = _create_snapshot_params(
            dc_coupled=True,
            active_base=create_realistic_load_profile(),
        )
        params_ac = _create_snapshot_params(
            dc_coupled=False,
            active_base=create_realistic_load_profile(),
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
        pv_data = create_synthetic_pv_data()

        params_limited = _create_snapshot_params(
            inverter_limit_kw=1.5,  # 1.5 kW limit with 2 kW peak PV
            active_base=[100] * 24,  # Low load to maximize surplus
        )
        params_unlimited = _create_snapshot_params(
            inverter_limit_kw=None,
            active_base=[100] * 24,
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
        params = _create_snapshot_params(
            active_base=create_realistic_load_profile(),
        )
        pv_data = create_synthetic_pv_data()
        return simulate(pv_data, cap_gross=5.0, params=params)

    def test_snapshot_seasonal_results(self, seasonal_result, snapshot: SnapshotAssertion):
        """Should match snapshot for seasonal scenario with 5kWh battery."""
        # when
        result_dict = _result_to_snapshot_dict(seasonal_result)

        # then
        assert result_dict == snapshot


class TestScenarioBaseLoadStrategy:
    """Snapshot tests for base_load discharge strategy."""

    @pytest.fixture(scope="class")
    def base_load_results(self) -> dict[str, SimulationResult]:
        """Run simulations with base_load strategy at different power levels."""
        pv_data = create_synthetic_pv_data()
        battery_capacity = 5.0

        results = {}
        for power_w in (100, 300):
            params = _create_snapshot_params(
                active_base=create_realistic_load_profile(),
                discharge_strategy_config=DischargeStrategyConfig(
                    mode="base_load", base_load_w=power_w,
                ),
            )
            results[f"base_load_{power_w}w"] = simulate(
                pv_data, cap_gross=battery_capacity, params=params,
            )
        return results

    def test_snapshot_base_load_100w(self, base_load_results, snapshot: SnapshotAssertion):
        """Should match snapshot for base_load 100W strategy."""
        # when
        result_dict = _result_to_snapshot_dict(base_load_results["base_load_100w"])

        # then
        assert result_dict == snapshot

    def test_snapshot_base_load_300w(self, base_load_results, snapshot: SnapshotAssertion):
        """Should match snapshot for base_load 300W strategy."""
        # when
        result_dict = _result_to_snapshot_dict(base_load_results["base_load_300w"])

        # then
        assert result_dict == snapshot


class TestScenarioTimeWindowStrategy:
    """Snapshot tests for time_window discharge strategy."""

    @pytest.fixture(scope="class")
    def time_window_result(self) -> SimulationResult:
        """Run simulation with evening time window strategy."""
        pv_data = create_synthetic_pv_data()
        params = _create_snapshot_params(
            active_base=create_realistic_load_profile(),
            discharge_strategy_config=DischargeStrategyConfig(
                mode="time_window",
                time_windows=(
                    TimeWindow(start_hour=17, end_hour=22, power_w=300),
                ),
            ),
        )
        return simulate(pv_data, cap_gross=5.0, params=params)

    def test_snapshot_time_window_evening(self, time_window_result, snapshot: SnapshotAssertion):
        """Should match snapshot for evening time window strategy."""
        # when
        result_dict = _result_to_snapshot_dict(time_window_result)

        # then
        assert result_dict == snapshot


class TestScenarioStrategyComparison:
    """Snapshot tests comparing all three strategies with identical setup."""

    @pytest.fixture(scope="class")
    def strategy_results(self) -> dict[str, SimulationResult]:
        """Run simulations with all three strategies for direct comparison."""
        pv_data = create_synthetic_pv_data()
        battery_capacity = 5.0
        load_profile = create_realistic_load_profile()

        strategies = {
            "zero_feed_in": DischargeStrategyConfig(mode="zero_feed_in"),
            "base_load_200w": DischargeStrategyConfig(mode="base_load", base_load_w=200),
            "time_window_evening": DischargeStrategyConfig(
                mode="time_window",
                time_windows=(TimeWindow(start_hour=17, end_hour=22, power_w=200),),
            ),
        }

        results = {}
        for name, strategy in strategies.items():
            params = _create_snapshot_params(
                active_base=load_profile,
                discharge_strategy_config=strategy,
            )
            results[name] = simulate(pv_data, cap_gross=battery_capacity, params=params)
        return results

    def test_snapshot_strategy_zero_feed_in(self, strategy_results, snapshot: SnapshotAssertion):
        """Should match snapshot for zero_feed_in in comparison scenario."""
        # when
        result_dict = _result_to_snapshot_dict(strategy_results["zero_feed_in"])

        # then
        assert result_dict == snapshot

    def test_snapshot_strategy_base_load_200w(self, strategy_results, snapshot: SnapshotAssertion):
        """Should match snapshot for base_load 200W in comparison scenario."""
        # when
        result_dict = _result_to_snapshot_dict(strategy_results["base_load_200w"])

        # then
        assert result_dict == snapshot

    def test_snapshot_strategy_time_window_evening(self, strategy_results, snapshot: SnapshotAssertion):
        """Should match snapshot for time_window evening in comparison scenario."""
        # when
        result_dict = _result_to_snapshot_dict(strategy_results["time_window_evening"])

        # then
        assert result_dict == snapshot


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
