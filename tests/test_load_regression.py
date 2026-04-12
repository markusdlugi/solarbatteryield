"""
Tests for the sub-hourly load regression module and its impact on simulation results.

The load regression module models the fact that household load varies within each hour.
This means that even when hourly averages suggest perfect PV-to-load matching, some
energy is fed into the grid during low-load moments and some is imported during high-load
moments within the same hour.

Run with:  python -m pytest tests/ -v
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

# Import shared helper functions from conftest
from conftest import (
    create_simulation_params,
    create_synthetic_pv_data,
)
from solarbatteryield.models import SimulationInput
from solarbatteryield.simulation import simulate
from solarbatteryield.simulation.load_regression import (
    get_direct_pv_fraction,
    _create_regression,
    _REGRESSION_DB,
    _DB_MAX_CONSUMPTION_W,
    DB_RESOLUTION_W,
)


def _create_load_regression_params() -> SimulationInput:
    """
    Create simulation parameters specific to load regression tests.
    
    Uses a realistic variable load profile and enables seasonal/flex features
    to test realistic scenarios.
    """
    return create_simulation_params(
        annual_kwh=2821,
        active_base=[
            190, 170, 170, 170, 170, 170, 340, 220,
            230, 370, 260, 1040, 250, 220, 190, 200,
            200, 900, 410, 270, 860, 340, 190, 200,
        ],
        seasonal_enabled=True,
        season_winter_pct=114,
        season_summer_pct=86,
        flex_enabled=True,
        flex_min_yield=5.0,
        flex_pool=3,
        flex_delta=[
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 110, 160, 0, 0, 410,
            530, -570, 0, 0, 0, 0, 0, 0,
        ],
        flex_refresh=0.5,
        periodic_enabled=True,
        periodic_delta=[
            350, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
        ],
        periodic_days=3,
    )


def _naive_fraction(load_w: float, pv_w: float, min_load_w: float = 0.0) -> float:
    """Naive approach: assumes all of min(load, pv) is self-consumed."""
    if load_w <= 0 or pv_w <= 0:
        return 0.0
    return 1.0


class TestRegressionDatabaseIntegrity:
    """Tests verifying the regression database is correctly loaded and structured."""

    def test_should_have_database_loaded(self):
        """Should have a non-empty regression database available."""
        # given
        database = _REGRESSION_DB

        # when
        count = len(database)

        # then
        assert count > 0

    def test_should_have_probability_distributions_summing_to_one(self):
        """Should have each load bin's probability distribution sum to approximately 1.0."""
        # given
        database = _REGRESSION_DB

        # when
        invalid_bins = []
        for bin_key, distribution in database.items():
            total = sum(probability for _, probability in distribution)
            if not (0.9999 <= total <= 1.0001):
                invalid_bins.append((bin_key, total))

        # then
        assert invalid_bins == []

    def test_should_cover_expected_load_range(self):
        """Should cover load range from 0 to 3450W in 50W steps."""
        # given
        database = _REGRESSION_DB

        # when
        keys = sorted(database.keys())

        # then
        assert keys[0] == 0
        assert keys[-1] == _DB_MAX_CONSUMPTION_W
        assert DB_RESOLUTION_W == 25
        assert len(keys) == 139


class TestDirectPvFractionEdgeCases:
    """Tests for edge case handling in direct PV fraction calculation."""

    @pytest.mark.parametrize("load_w,pv_w", [
        (0, 500),  # zero load
        (500, 0),  # zero PV
        (-100, 500),  # negative load
        (500, -100),  # negative PV
    ])
    def test_should_return_zero_for_invalid_inputs(self, load_w, pv_w):
        """Should return zero fraction for invalid input combinations."""
        # given
        # (parameters provided by decorator)

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w)

        # then
        assert fraction == pytest.approx(0.0)

    def test_should_handle_loads_above_database_range(self):
        """Should return valid fraction for loads exceeding the database maximum."""
        # given
        load_w = 5000  # Above 3450W max
        pv_w = 800

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w)

        # then
        assert 0.0 < fraction <= 1.0


class TestDirectPvFractionBehavior:
    """Tests for the behavioral characteristics of the direct PV fraction."""

    @pytest.mark.parametrize("load_w,pv_w", [
        (50, 50),
        (200, 500),
        (500, 200),
        (1000, 1000),
        (2000, 500),
    ])
    def test_should_return_fraction_between_zero_and_one(self, load_w, pv_w):
        """Should constrain fraction to valid probability range."""
        # given
        # (parameters provided by decorator)

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w)

        # then
        assert 0.0 <= fraction <= 1.0

    def test_should_return_less_than_one_when_pv_exceeds_load(self):
        """Should model that surplus PV cannot all be self-consumed due to load variability."""
        # given
        load_w, pv_w = 200, 800

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w)

        # then
        assert fraction < 1.0
        assert fraction > 0.5

    def test_should_return_less_than_one_when_load_exceeds_pv(self):
        """Should model that not all PV is consumed due to low-load moments within the hour."""
        # given
        load_w, pv_w = 800, 200

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w)

        # then
        assert fraction < 1.0
        assert fraction > 0.5

    def test_should_increase_absolute_direct_pv_with_more_pv_available(self):
        """Should increase absolute direct PV energy when more PV is available."""
        # given
        load = 300
        pv_low = 100
        pv_high = 500

        # when
        fraction_low = get_direct_pv_fraction(load, pv_low)
        fraction_high = get_direct_pv_fraction(load, pv_high)
        direct_low = fraction_low * min(load, pv_low)
        direct_high = fraction_high * min(load, pv_high)

        # then
        assert direct_high >= direct_low


class TestSyntheticRegressionGeneration:
    """Tests for synthetic regression distribution generation."""

    def test_should_generate_valid_distribution_for_high_loads(self):
        """Should create valid probability distribution for loads above database range."""
        # given
        high_load_w = 5000

        # when
        distribution, resolution = _create_regression(high_load_w)

        # then
        assert len(distribution) > 0
        assert resolution > 0
        total = sum(probability for _, probability in distribution)
        assert total == pytest.approx(1.0, abs=0.0001)


class TestSimulationWithRegression:
    """Tests comparing simulation behavior with and without load regression."""

    @pytest.fixture(scope="class")
    def simulation_results(self):
        """Run simulations with and without regression for comparison."""
        pv_data = create_synthetic_pv_data(peak_power_kw=0.6)
        params = _create_load_regression_params()
        battery_capacities = [0.0, 2.11, 4.22]

        results_regression = {}
        for cap in battery_capacities:
            results_regression[cap] = simulate(pv_data, cap, params)

        results_naive = {}
        with (
            patch("solarbatteryield.simulation.battery._no_battery.get_direct_pv_fraction",
                  side_effect=_naive_fraction),
            patch("solarbatteryield.simulation.battery._dc_coupled.get_direct_pv_fraction",
                  side_effect=_naive_fraction),
            patch("solarbatteryield.simulation.battery._ac_coupled.get_direct_pv_fraction",
                  side_effect=_naive_fraction),
        ):
            for cap in battery_capacities:
                results_naive[cap] = simulate(pv_data, cap, params)

        return {"regression": results_regression, "naive": results_naive}

    @pytest.mark.parametrize("battery_capacity", [0.0, 2.11, 4.22])
    def test_should_increase_grid_import_compared_to_naive(self, simulation_results, battery_capacity):
        """Should increase grid import when using regression due to load variability."""
        # given
        regression_result = simulation_results["regression"][battery_capacity]
        naive_result = simulation_results["naive"][battery_capacity]

        # when
        regression_import = regression_result.grid_import
        naive_import = naive_result.grid_import

        # then
        assert regression_import > naive_import

    def test_should_increase_feed_in_without_battery(self, simulation_results):
        """Should increase feed-in when no battery absorbs the surplus from low-load moments."""
        # given
        regression_result = simulation_results["regression"][0.0]
        naive_result = simulation_results["naive"][0.0]

        # when
        regression_feed_in = regression_result.feed_in
        naive_feed_in = naive_result.feed_in

        # then
        assert regression_feed_in > naive_feed_in

    @pytest.mark.parametrize("battery_capacity", [0.0, 2.11, 4.22])
    def test_should_preserve_total_consumption(self, simulation_results, battery_capacity):
        """Should not change total consumption regardless of regression model."""
        # given
        regression_result = simulation_results["regression"][battery_capacity]
        naive_result = simulation_results["naive"][battery_capacity]

        # when
        regression_consumption = regression_result.total_consumption
        naive_consumption = naive_result.total_consumption

        # then
        assert regression_consumption == pytest.approx(naive_consumption, abs=0.01)

    @pytest.mark.parametrize("battery_capacity", [0.0, 2.11, 4.22])
    def test_should_maintain_energy_balance(self, simulation_results, battery_capacity):
        """Should satisfy energy conservation: supply equals consumption."""
        # given
        result = simulation_results["regression"][battery_capacity]
        monthly = result.monthly

        # when
        total_direct_pv = sum(m.direct_pv for m in monthly.values())
        total_battery = sum(m.battery for m in monthly.values())
        total_grid = sum(m.grid_import for m in monthly.values())
        total_consumption = sum(m.consumption for m in monthly.values())
        supply = total_direct_pv + total_battery + total_grid

        # then
        assert supply == pytest.approx(total_consumption, abs=0.1)


class TestDirectPvFractionWithFloor:
    """Tests for the two-layer base load + variable load model."""

    def test_should_match_original_when_floor_is_zero(self):
        """Should produce identical results when min_load_w=0 (backwards compatible)."""
        # given
        load_w, pv_w = 300, 300

        # when
        fraction_with_zero_floor = get_direct_pv_fraction(load_w, pv_w, 0)
        fraction_without_floor = get_direct_pv_fraction(load_w, pv_w)

        # then
        assert fraction_with_zero_floor == fraction_without_floor

    def test_should_increase_fraction_with_higher_floor(self):
        """Should increase self-consumption fraction when floor is higher."""
        # given
        load_w, pv_w = 300, 300

        # when
        fraction_no_floor = get_direct_pv_fraction(load_w, pv_w, 0)
        fraction_with_floor = get_direct_pv_fraction(load_w, pv_w, 150)

        # then
        assert fraction_with_floor > fraction_no_floor

    def test_should_return_full_consumption_when_pv_below_floor(self):
        """Should return fraction=1.0 when PV ≤ floor (all PV consumed by base load)."""
        # given
        load_w, pv_w, floor = 300, 100, 150

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w, floor)

        # then
        assert fraction == pytest.approx(1.0)

    def test_should_increase_monotonically_with_floor(self):
        """Should increase fraction monotonically as floor increases."""
        # given
        load_w, pv_w = 300, 300
        floors = [0, 50, 100, 150, 200]

        # when
        fractions = [get_direct_pv_fraction(load_w, pv_w, f) for f in floors]

        # then
        for i in range(1, len(fractions)):
            assert fractions[i] >= fractions[i - 1]

    def test_should_handle_floor_above_load(self):
        """Should return valid fraction when floor exceeds load."""
        # given
        load_w, pv_w, floor = 100, 200, 500

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w, floor)

        # then
        assert 0.0 <= fraction <= 1.0

    def test_should_return_full_consumption_when_floor_equals_load(self):
        """Should return fraction=1.0 when floor equals load and PV covers it."""
        # given
        load_w, pv_w, floor = 200, 500, 200

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w, floor)

        # then
        assert fraction == pytest.approx(1.0)

    @pytest.mark.parametrize("load_w,pv_w,floor", [
        (0, 500, 100),
        (500, 0, 100),
        (-100, 500, 50),
    ])
    def test_should_return_zero_for_invalid_inputs_with_floor(self, load_w, pv_w, floor):
        """Should return zero for invalid inputs even with a floor."""
        # given
        # (parameters provided by decorator)

        # when
        fraction = get_direct_pv_fraction(load_w, pv_w, floor)

        # then
        assert fraction == pytest.approx(0.0)


class TestRegressionDatabaseReanalysis:
    """Validate the base-load-free regression database properties."""

    def test_should_have_distributions_summing_to_one(self):
        """Should have each load bin's probability distribution sum to ~1.0."""
        # given
        database = _REGRESSION_DB

        # when
        invalid_bins = []
        for key, dist in database.items():
            total = sum(p for _, p in dist)
            if not (0.999 <= total <= 1.001):
                invalid_bins.append((key, total))

        # then
        assert invalid_bins == [], f"Bins with invalid sums: {invalid_bins}"

    def test_should_have_low_zero_mass_for_medium_bins(self):
        """Should have small P(0W) mass for consumption bins >= 100W."""
        # given
        database = _REGRESSION_DB
        threshold = 0.05

        # when
        high_zero_mass_bins = []
        for key, dist in database.items():
            if key < 100:
                continue
            zero_mass = sum(p for power, p in dist if power == 0)
            if zero_mass >= threshold:
                high_zero_mass_bins.append((key, zero_mass))

        # then
        assert high_zero_mass_bins == [], f"Bins with high zero mass: {high_zero_mass_bins}"


class TestComputeMinLoadW:
    """Tests for the compute_min_load_w function."""

    def test_should_compute_floor_from_flat_profile(self):
        """Should compute floor as 200 * 0.9 = 180W for flat 200W profile."""
        # given
        from solarbatteryield.simulation.load import compute_min_load_w
        params = create_simulation_params(active_base=[200] * 24)

        # when
        floor = compute_min_load_w(params)

        # then
        assert floor == pytest.approx(180.0)

    def test_should_use_minimum_value_from_variable_profile(self):
        """Should compute floor based on minimum hourly value in variable profile."""
        # given
        from solarbatteryield.simulation.load import compute_min_load_w
        profile = [300] * 24
        profile[3] = 100  # Nighttime minimum
        params = create_simulation_params(active_base=profile)

        # when
        floor = compute_min_load_w(params)

        # then
        assert floor == pytest.approx(90.0)  # 100 * 0.9

    def test_should_apply_seasonal_scaling_before_ratio(self):
        """Should apply seasonal scaling before the 0.9 conversion factor."""
        # given
        from solarbatteryield.simulation.load import compute_min_load_w
        params = create_simulation_params(
            active_base=[200] * 24,
            seasonal_enabled=True,
            season_summer_pct=80,
        )

        # when
        floor = compute_min_load_w(params)

        # then
        assert floor == pytest.approx(200 * 0.8 * 0.9)

    def test_should_return_non_negative_floor(self):
        """Should never return negative floor value."""
        # given
        from solarbatteryield.simulation.load import compute_min_load_w
        params = create_simulation_params(active_base=[0] * 24)

        # when
        floor = compute_min_load_w(params)

        # then
        assert floor >= 0.0

    def test_should_produce_positive_floor_for_h0_profile(self):
        """Should produce positive floor for typical H0 profile consumption."""
        # given
        from solarbatteryield.simulation.load import compute_min_load_w
        params = create_simulation_params(annual_kwh=3000)

        # when
        floor = compute_min_load_w(params)

        # then
        assert floor > 0
        assert floor < 200  # Should be reasonable, not the full load

    def test_should_return_auto_value_regardless_of_override(self):
        """Should always return auto-computed value (override handled elsewhere)."""
        # given
        from solarbatteryield.simulation.load import compute_min_load_w
        params = create_simulation_params(active_base=[200] * 24)

        # when
        auto = compute_min_load_w(params)

        # then
        assert auto == pytest.approx(180.0)


class TestMinLoadWOverrideInSimulation:
    """Tests for the min_load_w override flowing through simulation."""

    def test_should_change_results_based_on_override_value(self):
        """Should produce different results when override values differ."""
        # given
        pv_data = create_synthetic_pv_data(peak_power_kw=0.6)
        params_no_override = create_simulation_params(
            active_base=[300] * 24,
            seasonal_enabled=False,
        )
        params_high_override = create_simulation_params(
            active_base=[300] * 24,
            seasonal_enabled=False,
            min_load_w_override=250.0,
        )
        params_zero_override = create_simulation_params(
            active_base=[300] * 24,
            seasonal_enabled=False,
            min_load_w_override=0.0,
        )

        # when
        result_auto = simulate(pv_data, 2.0, params_no_override)
        result_high = simulate(pv_data, 2.0, params_high_override)
        result_zero = simulate(pv_data, 2.0, params_zero_override)

        # then
        # Higher floor → less grid import (more self-consumption)
        assert result_high.grid_import <= result_auto.grid_import + 1.0
        # Zero floor → more grid import (less self-consumption)
        assert result_zero.grid_import >= result_high.grid_import


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
