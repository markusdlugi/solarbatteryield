"""
Tests for the expert mode (yearly profile) functionality.

These tests verify that the simulation correctly handles expert mode configurations
where users provide a complete yearly hourly load profile instead of using
standard profiles or custom daily patterns.
"""
import pytest
import numpy as np

from solarbatteryield.models import (
    SimulationConfig, ConsumptionConfig, LocationConfig,
    PVSystemConfig, StorageConfig, EconomicsConfig, SimulationParams,
)
from solarbatteryield.inverter_efficiency import DEFAULT_INVERTER_EFFICIENCY_CURVE
from solarbatteryield.simulation import simulate

# Import shared helper functions from conftest
from conftest import create_simulation_params


def _create_expert_params(yearly_profile: list[float] | None = None) -> SimulationParams:
    """Create SimulationParams configured for expert mode."""
    return create_simulation_params(
        inverter_efficiency_curve=((10, 0.91), (100, 0.96)),
        batt_inverter_efficiency_curve=DEFAULT_INVERTER_EFFICIENCY_CURVE,
        profile_mode="Experte",
        annual_kwh=None,
        yearly_profile=yearly_profile,
    )


def _create_expert_config(yearly_profile: list[float] | None = None) -> SimulationConfig:
    """Create SimulationConfig configured for expert mode."""
    return SimulationConfig(
        location=LocationConfig(lat=48.0, lon=11.0),
        consumption=ConsumptionConfig(
            profile_mode="Experte",
            yearly_profile=yearly_profile,
        ),
        pv_system=PVSystemConfig(),
        storage=StorageConfig(),
        economics=EconomicsConfig(),
    )


class TestExpertModeValidation:
    """Tests for configuration validation in expert mode."""

    def test_should_reject_expert_mode_without_yearly_profile(self):
        """Should mark configuration as invalid when expert mode has no yearly profile."""
        # given
        config = _create_expert_config(yearly_profile=None)

        # when
        is_valid, missing = config.is_valid()

        # then
        assert is_valid is False
        assert any("Jahreslastprofil" in m for m in missing)

    def test_should_reject_expert_mode_with_empty_yearly_profile(self):
        """Should mark configuration as invalid when expert mode has an empty profile."""
        # given
        config = _create_expert_config(yearly_profile=[])

        # when
        is_valid, missing = config.is_valid()

        # then
        assert is_valid is False
        assert any("Jahreslastprofil" in m for m in missing)

    def test_should_accept_expert_mode_with_valid_yearly_profile(self):
        """Should mark configuration as valid when expert mode has a complete profile."""
        # given
        config = _create_expert_config(yearly_profile=[100.0] * 8760)

        # when
        is_valid, missing = config.is_valid()

        # then
        assert is_valid is True
        assert len(missing) == 0


class TestExpertModeSimulation:
    """Tests for simulation behavior in expert mode."""

    def test_should_use_yearly_profile_values_for_consumption(self):
        """Should calculate consumption based on the provided yearly profile values."""
        # given
        constant_load_watts = 500.0
        yearly_profile = [constant_load_watts] * 8760
        params = _create_expert_params(yearly_profile=yearly_profile)
        pv_data = np.zeros(8760)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        expected_consumption = constant_load_watts / 1000 * 8760  # W -> kWh * hours
        assert result.total_consumption == pytest.approx(expected_consumption, rel=0.01)

    def test_should_apply_varying_yearly_profile_correctly(self):
        """Should handle varying hourly loads from the yearly profile."""
        # given
        yearly_profile = [float(i % 1000) for i in range(8760)]  # Varying 0-999W
        params = _create_expert_params(yearly_profile=yearly_profile)
        pv_data = np.zeros(8760)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        expected_consumption = sum(w / 1000 for w in yearly_profile)
        assert result.total_consumption == pytest.approx(expected_consumption, rel=0.01)

    def test_should_combine_yearly_profile_with_flex_load(self):
        """Should add flexible load delta to yearly profile when flex is active."""
        # given
        base_load_watts = 200.0
        flex_delta_watts = 500.0
        yearly_profile = [base_load_watts] * 8760
        params = _create_expert_params(yearly_profile=yearly_profile)
        params.flex_load_enabled = True
        params.flex_min_yield = 0.0  # Always trigger flex
        params.flex_delta = [flex_delta_watts] * 24
        params.flex_pool_size = 365  # Enough for every day

        # Create PV data that triggers flex load every day
        pv_data = np.array([0.5 if h % 24 in range(6, 18) else 0.0 for h in range(8760)])

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        # Consumption should be higher than base due to flex load additions
        base_only = base_load_watts / 1000 * 8760
        assert result.total_consumption > base_only

    def test_should_combine_yearly_profile_with_periodic_load(self):
        """Should add periodic load delta on scheduled days."""
        # given
        base_load_watts = 200.0
        periodic_delta_watts = 300.0
        yearly_profile = [base_load_watts] * 8760
        params = _create_expert_params(yearly_profile=yearly_profile)
        params.periodic_load_enabled = True
        params.periodic_interval_days = 1  # Every day
        params.periodic_delta = [periodic_delta_watts] * 24
        pv_data = np.zeros(8760)

        # when
        result = simulate(pv_data, cap_gross=0.0, params=params)

        # then
        expected_per_hour = (base_load_watts + periodic_delta_watts) / 1000
        expected_total = expected_per_hour * 8760
        assert result.total_consumption == pytest.approx(expected_total, rel=0.01)


class TestExpertModeWithBattery:
    """Tests for expert mode simulation with battery storage."""

    def test_should_charge_battery_from_pv_surplus(self):
        """Should store excess PV generation in battery when available."""
        # given
        load_watts = 200.0
        yearly_profile = [load_watts] * 8760
        params = _create_expert_params(yearly_profile=yearly_profile)
        
        # PV generates 1kW during day, nothing at night
        pv_data = np.array([1.0 if 6 <= h % 24 < 18 else 0.0 for h in range(8760)])

        # when
        result_no_battery = simulate(pv_data, cap_gross=0.0, params=params)
        result_with_battery = simulate(pv_data, cap_gross=5.0, params=params)

        # then
        # With battery, less should be fed in and more self-consumed
        assert result_with_battery.feed_in < result_no_battery.feed_in
        assert result_with_battery.grid_import < result_no_battery.grid_import

    def test_should_discharge_battery_to_cover_evening_load(self):
        """Should use stored battery energy to cover load when PV is unavailable."""
        # given
        load_watts = 500.0
        yearly_profile = [load_watts] * 8760
        params = _create_expert_params(yearly_profile=yearly_profile)
        
        # PV only during midday hours
        pv_data = np.array([2.0 if 10 <= h % 24 < 14 else 0.0 for h in range(8760)])

        # when
        result_no_battery = simulate(pv_data, cap_gross=0.0, params=params)
        result_with_battery = simulate(pv_data, cap_gross=5.0, params=params)

        # then
        # Battery should reduce grid import during non-PV hours
        assert result_with_battery.grid_import < result_no_battery.grid_import


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
