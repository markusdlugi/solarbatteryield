"""
Tests for the inverter efficiency module.

The inverter efficiency module provides power-dependent efficiency curves
based on CEC (California Energy Commission) data, allowing the simulation
to model realistic inverter behavior at different power levels.
"""
import pytest

from solarbatteryield.inverter_efficiency import (
    get_inverter_efficiency,
    INVERTER_EFFICIENCY_CURVES,
    INVERTER_EFFICIENCY_P10,
    INVERTER_EFFICIENCY_P50,
    INVERTER_EFFICIENCY_P90,
    DEFAULT_INVERTER_EFFICIENCY_CURVE,
    DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT,
)


class TestEfficiencyCurveData:
    """Tests verifying the efficiency curve data is correctly structured."""

    def test_should_have_all_preset_curves_available(self):
        """Should have pessimistic, median, and optimistic curves defined."""
        # given
        expected_presets = ["pessimistic", "median", "optimistic"]

        # when
        available_presets = list(INVERTER_EFFICIENCY_CURVES.keys())

        # then
        assert available_presets == expected_presets

    @pytest.mark.parametrize("curve_name", ["pessimistic", "median", "optimistic"])
    def test_should_have_six_efficiency_points_per_curve(self, curve_name):
        """Should have efficiency values for 10%, 20%, 30%, 50%, 75%, 100% power levels."""
        # given
        expected_thresholds = [10, 20, 30, 50, 75, 100]
        curve = INVERTER_EFFICIENCY_CURVES[curve_name]

        # when
        thresholds = [t for t, _ in curve]

        # then
        assert thresholds == expected_thresholds

    @pytest.mark.parametrize("curve_name", ["pessimistic", "median", "optimistic"])
    def test_should_have_valid_efficiency_values(self, curve_name):
        """Should have efficiency values between 0.85 and 1.0 (realistic range)."""
        # given
        curve = INVERTER_EFFICIENCY_CURVES[curve_name]

        # when
        efficiencies = [eff for _, eff in curve]

        # then
        for eff in efficiencies:
            assert 0.85 <= eff <= 1.0

    @pytest.mark.parametrize("threshold_idx", range(6))
    def test_should_have_optimistic_higher_than_pessimistic(self, threshold_idx):
        """Should have optimistic curve consistently above pessimistic curve."""
        # given
        pessimistic = INVERTER_EFFICIENCY_P10
        optimistic = INVERTER_EFFICIENCY_P90

        # when
        threshold_pess, eff_pess = pessimistic[threshold_idx]
        threshold_opt, eff_opt = optimistic[threshold_idx]

        # then
        assert threshold_pess == threshold_opt  # Same thresholds
        assert eff_opt > eff_pess

    @pytest.mark.parametrize("threshold_idx", range(6))
    def test_should_have_median_between_pessimistic_and_optimistic(self, threshold_idx):
        """Should have median curve between pessimistic and optimistic."""
        # given
        pessimistic = INVERTER_EFFICIENCY_P10
        median = INVERTER_EFFICIENCY_P50
        optimistic = INVERTER_EFFICIENCY_P90

        # when
        _, eff_pess = pessimistic[threshold_idx]
        _, eff_med = median[threshold_idx]
        _, eff_opt = optimistic[threshold_idx]

        # then
        assert eff_pess <= eff_med <= eff_opt

    def test_should_have_default_curve_equal_to_median(self):
        """Should use median (P50) as the default efficiency curve."""
        # given/when
        default = DEFAULT_INVERTER_EFFICIENCY_CURVE

        # then
        assert default == INVERTER_EFFICIENCY_P50

    def test_should_have_custom_defaults_derived_from_median(self):
        """Should have custom default percentages derived from median curve."""
        # given
        median_efficiencies = [eff for _, eff in INVERTER_EFFICIENCY_P50]
        expected_percentages = [round(eff * 100, 2) for eff in median_efficiencies]

        # when
        custom_defaults = DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT

        # then
        assert custom_defaults == expected_percentages


class TestGetInverterEfficiency:
    """Tests for the get_inverter_efficiency function."""

    def test_should_return_correct_efficiency_at_10_percent_load(self):
        """Should return 10% threshold efficiency when power is at 10% of capacity."""
        # given
        max_power = 1.0
        power = 0.1  # 10% of capacity

        # when
        efficiency = get_inverter_efficiency(power, max_power)

        # then
        expected = INVERTER_EFFICIENCY_P50[0][1]  # First threshold
        assert efficiency == expected

    def test_should_return_correct_efficiency_at_50_percent_load(self):
        """Should return 50% threshold efficiency when power is at 50% of capacity."""
        # given
        max_power = 2.0
        power = 1.0  # 50% of capacity

        # when
        efficiency = get_inverter_efficiency(power, max_power)

        # then
        expected = INVERTER_EFFICIENCY_P50[3][1]  # 50% threshold
        assert efficiency == expected

    def test_should_return_100_percent_efficiency_at_full_load(self):
        """Should return 100% threshold efficiency when at full capacity."""
        # given
        max_power = 0.8
        power = 0.8  # 100% of capacity

        # when
        efficiency = get_inverter_efficiency(power, max_power)

        # then
        expected = INVERTER_EFFICIENCY_P50[5][1]  # 100% threshold
        assert efficiency == expected

    def test_should_return_peak_efficiency_when_no_max_power_defined(self):
        """Should return 50% efficiency (peak) when max_power is None or zero."""
        # given
        power = 0.5

        # when
        efficiency_none = get_inverter_efficiency(power, None)
        efficiency_zero = get_inverter_efficiency(power, 0)

        # then
        expected = INVERTER_EFFICIENCY_P50[3][1]  # 50% threshold (peak)
        assert efficiency_none == expected
        assert efficiency_zero == expected

    def test_should_cap_power_percentage_at_100(self):
        """Should cap power percentage at 100% even if power exceeds max_power."""
        # given
        max_power = 0.5
        power = 1.0  # 200% of capacity (impossible in practice but valid input)

        # when
        efficiency = get_inverter_efficiency(power, max_power)

        # then
        expected = INVERTER_EFFICIENCY_P50[5][1]  # 100% threshold
        assert efficiency == expected

    def test_should_use_custom_curve_when_provided(self):
        """Should use provided custom efficiency curve instead of default."""
        # given
        custom_curve = ((10, 0.80), (20, 0.85), (30, 0.88), (50, 0.90), (75, 0.89), (100, 0.87))
        max_power = 1.0
        power = 0.1  # 10% of capacity

        # when
        efficiency = get_inverter_efficiency(power, max_power, custom_curve)

        # then
        assert efficiency == 0.80

    def test_should_use_pessimistic_curve_correctly(self):
        """Should return lower efficiency when using pessimistic curve."""
        # given
        max_power = 1.0
        power = 0.5
        pessimistic = INVERTER_EFFICIENCY_CURVES["pessimistic"]
        optimistic = INVERTER_EFFICIENCY_CURVES["optimistic"]

        # when
        eff_pessimistic = get_inverter_efficiency(power, max_power, pessimistic)
        eff_optimistic = get_inverter_efficiency(power, max_power, optimistic)

        # then
        assert eff_pessimistic < eff_optimistic

    @pytest.mark.parametrize("power_pct,expected_threshold_idx", [
        (5, 0),    # Below 10% -> use 10% efficiency
        (10, 0),   # Exactly 10% -> use 10% efficiency
        (15, 1),   # Between 10% and 20% -> use 20% efficiency
        (25, 2),   # Between 20% and 30% -> use 30% efficiency
        (40, 3),   # Between 30% and 50% -> use 50% efficiency
        (60, 4),   # Between 50% and 75% -> use 75% efficiency
        (80, 5),   # Between 75% and 100% -> use 100% efficiency
        (100, 5),  # Exactly 100% -> use 100% efficiency
    ])
    def test_should_select_correct_threshold(self, power_pct, expected_threshold_idx):
        """Should select the correct efficiency based on power percentage."""
        # given
        max_power = 1.0
        power = power_pct / 100

        # when
        efficiency = get_inverter_efficiency(power, max_power)

        # then
        expected = INVERTER_EFFICIENCY_P50[expected_threshold_idx][1]
        assert efficiency == expected


class TestEfficiencyCurveBehavior:
    """Tests for realistic efficiency curve behavior patterns."""

    def test_should_have_lower_efficiency_at_very_low_load(self):
        """Should have lower efficiency at 10% load compared to 50% load."""
        # given
        max_power = 1.0
        power_10pct = 0.1
        power_50pct = 0.5

        # when
        eff_10 = get_inverter_efficiency(power_10pct, max_power)
        eff_50 = get_inverter_efficiency(power_50pct, max_power)

        # then
        assert eff_10 < eff_50

    def test_should_have_peak_efficiency_near_50_percent(self):
        """Should have peak efficiency at or near 50% load level."""
        # given
        max_power = 1.0
        efficiencies = []
        for pct in [10, 20, 30, 50, 75, 100]:
            power = pct / 100
            eff = get_inverter_efficiency(power, max_power)
            efficiencies.append((pct, eff))

        # when
        peak_pct, peak_eff = max(efficiencies, key=lambda x: x[1])

        # then
        # Peak should be at 50% or nearby (50% or 75% for P50 curve)
        assert peak_pct in [50, 75]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

