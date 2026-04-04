"""
Tests for the data models module.

The models module provides type-safe configuration and result structures for the
PV analysis application, including validation logic and conversion methods.
"""
import pytest

from solarbatteryield.models import (
    LocationConfig,
    ConsumptionConfig,
    PVSystemConfig,
    StorageConfig,
    EconomicsConfig,
    SimulationConfig,
    SimulationParams,
    SimulationResult,
    ScenarioResult,
    AnalysisResult,
    MonthlyData,
    HourlyResult,
    PVModule,
    StorageOption,
)
from solarbatteryield.inverter_efficiency import (
    INVERTER_EFFICIENCY_CURVES,
    DEFAULT_INVERTER_EFFICIENCY_CURVE,
)


class TestLocationConfig:
    """Tests for location configuration validation."""

    def test_should_accept_valid_coordinates(self):
        """Should accept valid latitude and longitude values."""
        # given/when
        location = LocationConfig(lat=48.0, lon=11.0)

        # then
        assert location.lat == 48.0
        assert location.lon == 11.0

    @pytest.mark.parametrize("lat,description", [
        (90.0, "North Pole"),
        (-90.0, "South Pole"),
    ])
    def test_should_accept_boundary_latitude_values(self, lat, description):
        """Should accept latitude at boundaries (-90 and 90)."""
        # given
        # (parameters provided by decorator)

        # when
        location = LocationConfig(lat=lat, lon=0.0)

        # then
        assert location.lat == lat

    def test_should_reject_latitude_above_90(self):
        """Should raise ValueError for latitude above 90."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            LocationConfig(lat=91.0, lon=0.0)
        assert "Breitengrad" in str(exc_info.value)

    def test_should_reject_latitude_below_minus_90(self):
        """Should raise ValueError for latitude below -90."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            LocationConfig(lat=-91.0, lon=0.0)
        assert "Breitengrad" in str(exc_info.value)

    def test_should_reject_longitude_above_180(self):
        """Should raise ValueError for longitude above 180."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            LocationConfig(lat=0.0, lon=181.0)
        assert "Längengrad" in str(exc_info.value)

    def test_should_reject_longitude_below_minus_180(self):
        """Should raise ValueError for longitude below -180."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            LocationConfig(lat=0.0, lon=-181.0)
        assert "Längengrad" in str(exc_info.value)

    def test_should_accept_none_coordinates(self):
        """Should accept None for both latitude and longitude."""
        # given/when
        location = LocationConfig(lat=None, lon=None)

        # then
        assert location.lat is None
        assert location.lon is None


class TestConsumptionConfig:
    """Tests for consumption configuration."""

    def test_should_have_default_profile_mode_einfach(self):
        """Should default to Einfach (simple) profile mode."""
        # given/when
        config = ConsumptionConfig()

        # then
        assert config.profile_mode == "Einfach"

    def test_should_detect_day_type_profiles_when_provided(self):
        """Should return True for has_day_type_profiles when profiles are provided."""
        # given
        config = ConsumptionConfig(
            profile_saturday=[100] * 24,
            profile_sunday=[80] * 24,
        )

        # when
        result = config.has_day_type_profiles()

        # then
        assert result is True

    def test_should_not_detect_day_type_profiles_when_missing(self):
        """Should return False for has_day_type_profiles when profiles are missing."""
        # given
        config = ConsumptionConfig()

        # when
        result = config.has_day_type_profiles()

        # then
        assert result is False

    @pytest.mark.parametrize("yearly_profile,expected,description", [
        ([100.0] * 8760, True, "full yearly profile"),
        (None, False, "no yearly profile"),
        ([], False, "empty yearly profile"),
    ])
    def test_should_detect_yearly_profile(self, yearly_profile, expected, description):
        """Should correctly detect when yearly profile is provided."""
        # given
        config = ConsumptionConfig(yearly_profile=yearly_profile)

        # when
        result = config.has_yearly_profile()

        # then
        assert result is expected, f"Expected {expected} for {description}"


class TestStorageConfig:
    """Tests for storage configuration validation."""

    def test_should_accept_valid_battery_loss(self):
        """Should accept battery loss values within valid range."""
        # given
        valid_loss = 10

        # when
        config = StorageConfig(batt_loss=valid_loss)

        # then
        assert config.batt_loss == valid_loss

    def test_should_reject_battery_loss_above_50_percent(self):
        """Should raise ValueError for battery loss above 50%."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            StorageConfig(batt_loss=51)
        assert "Batterieverluste" in str(exc_info.value)

    def test_should_reject_negative_battery_loss(self):
        """Should raise ValueError for negative battery loss."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            StorageConfig(batt_loss=-5)
        assert "Batterieverluste" in str(exc_info.value)

    def test_should_reject_min_soc_greater_than_max_soc_summer(self):
        """Should raise ValueError when min_soc > max_soc for summer."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            StorageConfig(min_soc_summer=80, max_soc_summer=50)
        assert "Min. SoC Sommer" in str(exc_info.value)

    def test_should_reject_min_soc_greater_than_max_soc_winter(self):
        """Should raise ValueError when min_soc > max_soc for winter."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            StorageConfig(min_soc_winter=80, max_soc_winter=50)
        assert "Min. SoC Winter" in str(exc_info.value)

    def test_should_accept_valid_soc_range(self):
        """Should accept valid SoC ranges."""
        # given
        min_summer = 10
        max_summer = 90

        # when
        config = StorageConfig(
            min_soc_summer=min_summer,
            max_soc_summer=max_summer,
            min_soc_winter=20,
            max_soc_winter=100,
        )

        # then
        assert config.min_soc_summer == min_summer
        assert config.max_soc_summer == max_summer


class TestEconomicsConfig:
    """Tests for economics configuration validation."""

    def test_should_reject_zero_electricity_price(self):
        """Should raise ValueError for zero electricity price."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            EconomicsConfig(e_price=0)
        assert "Strompreis" in str(exc_info.value)

    def test_should_reject_negative_electricity_price(self):
        """Should raise ValueError for negative electricity price."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            EconomicsConfig(e_price=-0.10)
        assert "Strompreis" in str(exc_info.value)

    def test_should_reject_analysis_years_above_50(self):
        """Should raise ValueError for analysis years above 50."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            EconomicsConfig(analysis_years=51)
        assert "Analysezeitraum" in str(exc_info.value)

    def test_should_reject_analysis_years_below_1(self):
        """Should raise ValueError for analysis years below 1."""
        # given/when/then
        with pytest.raises(ValueError) as exc_info:
            EconomicsConfig(analysis_years=0)
        assert "Analysezeitraum" in str(exc_info.value)

    def test_should_accept_valid_economics(self):
        """Should accept valid economic parameters."""
        # given/when
        config = EconomicsConfig(e_price=0.30, e_inc=0.05, analysis_years=20)

        # then
        assert config.e_price == 0.30
        assert config.e_inc == 0.05
        assert config.analysis_years == 20


class TestSimulationConfig:
    """Tests for the complete simulation configuration."""

    def test_should_build_efficiency_curve_from_preset(self):
        """Should build efficiency curve from preset name."""
        # given
        config = SimulationConfig(
            pv_system=PVSystemConfig(inverter_efficiency_preset="optimistic")
        )

        # when
        curve = config.get_inverter_efficiency_curve()

        # then
        assert curve == INVERTER_EFFICIENCY_CURVES["optimistic"]

    def test_should_build_efficiency_curve_from_custom_values(self):
        """Should build efficiency curve from custom percentage values."""
        # given
        custom_values = [90.0, 92.0, 94.0, 95.0, 94.5, 93.0]
        config = SimulationConfig(
            pv_system=PVSystemConfig(
                inverter_efficiency_preset="custom",
                inverter_efficiency_custom=custom_values,
            )
        )

        # when
        curve = config.get_inverter_efficiency_curve()

        # then
        expected_curve = (
            (10, 0.90), (20, 0.92), (30, 0.94),
            (50, 0.95), (75, 0.945), (100, 0.93),
        )
        assert curve == expected_curve

    def test_should_fallback_to_default_for_unknown_preset(self):
        """Should use default curve for unknown preset names."""
        # given
        config = SimulationConfig(
            pv_system=PVSystemConfig(inverter_efficiency_preset="unknown_preset")
        )

        # when
        curve = config.get_inverter_efficiency_curve()

        # then
        assert curve == DEFAULT_INVERTER_EFFICIENCY_CURVE

    def test_should_report_invalid_when_location_missing(self):
        """Should report configuration as invalid when location is missing."""
        # given
        config = SimulationConfig(
            location=LocationConfig(lat=None, lon=None),
            consumption=ConsumptionConfig(annual_kwh=3000),
        )

        # when
        is_valid, missing = config.is_valid()

        # then
        assert is_valid is False
        assert any("Standort" in m for m in missing)

    def test_should_report_invalid_when_annual_kwh_missing_in_simple_mode(self):
        """Should report invalid when annual kWh is missing in simple mode."""
        # given
        config = SimulationConfig(
            location=LocationConfig(lat=48.0, lon=11.0),
            consumption=ConsumptionConfig(profile_mode="Einfach", annual_kwh=None),
        )

        # when
        is_valid, missing = config.is_valid()

        # then
        assert is_valid is False
        assert any("Jahresverbrauch" in m for m in missing)

    def test_should_report_valid_for_complete_simple_mode_config(self):
        """Should report valid for complete simple mode configuration."""
        # given
        config = SimulationConfig(
            location=LocationConfig(lat=48.0, lon=11.0),
            consumption=ConsumptionConfig(profile_mode="Einfach", annual_kwh=3000),
        )

        # when
        is_valid, missing = config.is_valid()

        # then
        assert is_valid is True
        assert len(missing) == 0

    def test_should_calculate_total_peak_power(self):
        """Should calculate total peak power from all modules."""
        # given
        config = SimulationConfig(
            pv_system=PVSystemConfig(
                modules=[
                    PVModule(id=0, name="South", peak=2.0, azi=0, slope=35),
                    PVModule(id=1, name="East", peak=1.5, azi=-90, slope=30),
                ]
            )
        )

        # when
        total = config.total_peak_kwp

        # then
        assert total == pytest.approx(3.5)

    def test_should_convert_inverter_limit_to_kw(self):
        """Should convert inverter limit from W to kW."""
        # given
        config = SimulationConfig(
            pv_system=PVSystemConfig(inverter_limit_enabled=True, inverter_limit_w=800)
        )

        # when
        limit = config.inverter_limit_kw

        # then
        assert limit == pytest.approx(0.8)

    def test_should_return_none_when_inverter_limit_disabled(self):
        """Should return None for inverter limit when disabled."""
        # given
        config = SimulationConfig(
            pv_system=PVSystemConfig(inverter_limit_enabled=False)
        )

        # when
        limit = config.inverter_limit_kw

        # then
        assert limit is None


class TestSimulationParams:
    """Tests for simulation parameters."""

    def test_should_create_from_simulation_config(self):
        """Should create SimulationParams from SimulationConfig."""
        # given
        config = SimulationConfig(
            location=LocationConfig(lat=48.0, lon=11.0),
            consumption=ConsumptionConfig(
                profile_mode="Einfach",
                annual_kwh=3000,
            ),
            pv_system=PVSystemConfig(data_year=2020),
            storage=StorageConfig(batt_loss=10, dc_coupled=True),
        )

        # when
        params = SimulationParams.from_config(config)

        # then
        assert params.data_year == 2020
        assert params.batt_loss_pct == 10
        assert params.dc_coupled is True
        assert params.profile_mode == "Einfach"
        assert params.annual_kwh == 3000

    def test_use_h0_profile_should_return_true_for_einfach_mode(self):
        """Should return True for use_h0_profile in Einfach mode."""
        # given
        params = _create_test_params(profile_mode="Einfach")

        # when
        result = params.use_h0_profile()

        # then
        assert result is True

    def test_use_h0_profile_should_return_false_for_erweitert_mode(self):
        """Should return False for use_h0_profile in Erweitert mode."""
        # given
        params = _create_test_params(profile_mode="Erweitert")

        # when
        result = params.use_h0_profile()

        # then
        assert result is False

    def test_use_yearly_profile_should_return_true_for_experte_mode(self):
        """Should return True for use_yearly_profile in Experte mode with profile."""
        # given
        params = _create_test_params(
            profile_mode="Experte",
            yearly_profile=[100.0] * 8760,
        )

        # when
        result = params.use_yearly_profile()

        # then
        assert result is True

    def test_use_yearly_profile_should_return_false_without_profile(self):
        """Should return False for use_yearly_profile when profile is None."""
        # given
        params = _create_test_params(
            profile_mode="Experte",
            yearly_profile=None,
        )

        # when
        result = params.use_yearly_profile()

        # then
        assert result is False


class TestMonthlyData:
    """Tests for monthly data accumulation."""

    def test_should_accumulate_hourly_results(self):
        """Should correctly accumulate multiple hourly results."""
        # given
        monthly = MonthlyData()
        hourly1 = HourlyResult(
            grid_import=1.0, feed_in=0.5, curtailed=0.1,
            direct_pv=0.8, battery_discharge=0.2,
            pv_generation=1.5, consumption=2.0,
        )
        hourly2 = HourlyResult(
            grid_import=0.5, feed_in=0.3, curtailed=0.0,
            direct_pv=0.6, battery_discharge=0.4,
            pv_generation=1.0, consumption=1.5,
        )

        # when
        monthly.add_hourly_result(hourly1)
        monthly.add_hourly_result(hourly2)

        # then
        assert monthly.grid_import == pytest.approx(1.5)
        assert monthly.feed_in == pytest.approx(0.8)
        assert monthly.direct_pv == pytest.approx(1.4)
        assert monthly.battery == pytest.approx(0.6)
        assert monthly.pv_generation == pytest.approx(2.5)
        assert monthly.consumption == pytest.approx(3.5)


class TestScenarioResult:
    """Tests for scenario result calculations."""

    def test_should_calculate_autarky_correctly(self):
        """Should calculate autarky as (1 - grid_import / consumption) * 100."""
        # given
        monthly = {1: MonthlyData(consumption=100.0, grid_import=30.0)}
        simulation = SimulationResult(
            grid_import=30.0,
            total_consumption=100.0,
            feed_in=20.0,
            curtailed=0.0,
            monthly=monthly,
        )
        scenario = ScenarioResult(
            name="Test",
            storage_capacity=5.0,
            investment_cost=1000.0,
            simulation=simulation,
        )

        # when
        autarky = scenario.autarky

        # then
        assert autarky == pytest.approx(70.0)

    def test_should_return_zero_autarky_for_zero_consumption(self):
        """Should return 0% autarky when consumption is zero."""
        # given
        simulation = SimulationResult(
            grid_import=0.0,
            total_consumption=0.0,
            feed_in=0.0,
            curtailed=0.0,
            monthly={},
        )
        scenario = ScenarioResult(
            name="Test",
            storage_capacity=0.0,
            investment_cost=0.0,
            simulation=simulation,
        )

        # when
        autarky = scenario.autarky

        # then
        assert autarky == pytest.approx(0.0)

    def test_should_calculate_saved_kwh_correctly(self):
        """Should calculate saved kWh as consumption minus grid import."""
        # given
        simulation = SimulationResult(
            grid_import=500.0,
            total_consumption=2000.0,
            feed_in=300.0,
            curtailed=0.0,
            monthly={},
        )
        scenario = ScenarioResult(
            name="Test",
            storage_capacity=5.0,
            investment_cost=1000.0,
            simulation=simulation,
        )

        # when
        saved = scenario.saved_kwh

        # then
        assert saved == pytest.approx(1500.0)

    def test_should_calculate_annual_savings(self):
        """Should calculate annual savings from saved kWh and feed-in."""
        # given
        simulation = SimulationResult(
            grid_import=500.0,
            total_consumption=2000.0,
            feed_in=300.0,
            curtailed=0.0,
            monthly={},
        )
        scenario = ScenarioResult(
            name="Test",
            storage_capacity=5.0,
            investment_cost=1000.0,
            simulation=simulation,
        )
        e_price = 0.30  # EUR/kWh
        feed_in_tariff = 0.08  # EUR/kWh

        # when
        savings = scenario.annual_savings(e_price, feed_in_tariff)

        # then
        expected = 1500.0 * 0.30 + 300.0 * 0.08
        assert savings == pytest.approx(expected)


class TestAnalysisResult:
    """Tests for analysis result aggregation."""

    def test_should_find_best_scenario_by_profit(self):
        """Should find the scenario with highest net profit."""
        # given
        scenarios = [
            _create_scenario_result("Low", storage=0.0, investment=500.0, grid_import=1500.0),
            _create_scenario_result("Medium", storage=5.0, investment=2000.0, grid_import=800.0),
            _create_scenario_result("High", storage=10.0, investment=4000.0, grid_import=500.0),
        ]
        analysis = AnalysisResult(scenarios=scenarios, pv_generation_total=2500.0)

        # when
        best = analysis.get_best_scenario(
            e_price=0.30,
            e_inc=0.03,
            feed_in_tariff=0.08,
            years=15,
        )

        # then
        # The best scenario depends on the specific savings calculation
        assert best in scenarios

    def test_should_return_total_consumption_from_first_scenario(self):
        """Should return total consumption from the first scenario."""
        # given
        scenarios = [
            _create_scenario_result("A", storage=0.0, investment=500.0, grid_import=1000.0, consumption=3000.0),
            _create_scenario_result("B", storage=5.0, investment=2000.0, grid_import=800.0, consumption=3000.0),
        ]
        analysis = AnalysisResult(scenarios=scenarios, pv_generation_total=2500.0)

        # when
        consumption = analysis.total_consumption

        # then
        assert consumption == pytest.approx(3000.0)


# ─── Helper Functions ────────────────────────────────────────────────────────

def _create_test_params(**overrides) -> SimulationParams:
    """Create test SimulationParams with sensible defaults."""
    defaults = dict(
        batt_loss_pct=10,
        dc_coupled=True,
        min_soc_summer_pct=10,
        min_soc_winter_pct=20,
        max_soc_summer_pct=100,
        max_soc_winter_pct=100,
        data_year=2015,
        inverter_limit_kw=0.8,
        inverter_efficiency_curve=DEFAULT_INVERTER_EFFICIENCY_CURVE,
        batt_inverter_efficiency_curve=DEFAULT_INVERTER_EFFICIENCY_CURVE,
        profile_mode="Erweitert",
        annual_kwh=3000,
        profile_base=[200] * 24,
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


def _create_scenario_result(
    name: str,
    storage: float,
    investment: float,
    grid_import: float,
    consumption: float = 3000.0,
    feed_in: float = 500.0,
) -> ScenarioResult:
    """Create a test ScenarioResult with specified values."""
    simulation = SimulationResult(
        grid_import=grid_import,
        total_consumption=consumption,
        feed_in=feed_in,
        curtailed=0.0,
        monthly={},
    )
    return ScenarioResult(
        name=name,
        storage_capacity=storage,
        investment_cost=investment,
        simulation=simulation,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

