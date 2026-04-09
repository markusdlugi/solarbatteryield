"""
Tests for the report context module.

Tests the ReportContext class that provides shared data for report components.
"""
import pytest

from solarbatteryield.report.context import ReportContext
from solarbatteryield.models import (
    SimulationConfig, LocationConfig, ConsumptionConfig, PVSystemConfig,
    StorageConfig, EconomicsConfig, AnalysisResult, ScenarioResult,
    SimulationResult, MonthlyData, PVModule
)


def _create_test_config(**overrides) -> SimulationConfig:
    """Create a test SimulationConfig with sensible defaults."""
    defaults = {
        "location": LocationConfig(lat=48.1371, lon=11.5754),
        "consumption": ConsumptionConfig(
            profile_mode="Einfach",
            annual_kwh=3000.0,
        ),
        "pv_system": PVSystemConfig(
            data_year=2015,
            modules=[PVModule(id=0, name="Test", peak=2.0, azi=0, slope=30)],
        ),
        "storage": StorageConfig(),
        "economics": EconomicsConfig(
            e_price=0.30,
            e_inc=0.03,
            etf_ret=0.07,
            feed_in_tariff=8.0,
            reinvest_savings=False,
            analysis_years=15,
        ),
    }
    defaults.update(overrides)
    return SimulationConfig(**defaults)


def _create_test_results(
    grid_import: float = 1500.0,
    total_consumption: float = 3000.0,
    feed_in: float = 500.0,
    pv_generation_total: float = 2500.0,
) -> AnalysisResult:
    """Create a test AnalysisResult with sensible defaults."""
    monthly = {m: MonthlyData() for m in range(1, 13)}
    sim_result = SimulationResult(
        grid_import=grid_import,
        total_consumption=total_consumption,
        feed_in=feed_in,
        curtailed=0.0,
        monthly=monthly,
    )
    scenario = ScenarioResult(
        name="Test Scenario",
        storage_capacity=2.0,
        investment_cost=1000,
        simulation=sim_result,
    )
    return AnalysisResult(
        scenarios=[scenario],
        pv_generation_total=pv_generation_total,
    )


class TestReportContextProperties:
    """Tests for ReportContext property accessors."""

    def test_should_provide_electricity_price(self):
        """Should provide access to electricity price from economics config."""
        # given
        config = _create_test_config(
            economics=EconomicsConfig(e_price=0.35)
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        e_price = ctx.e_price

        # then
        assert e_price == pytest.approx(0.35)

    def test_should_provide_electricity_price_increase(self):
        """Should provide access to annual price increase rate."""
        # given
        config = _create_test_config(
            economics=EconomicsConfig(e_inc=0.05)
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        e_inc = ctx.e_inc

        # then
        assert e_inc == pytest.approx(0.05)

    def test_should_provide_etf_return(self):
        """Should provide access to ETF return rate."""
        # given
        config = _create_test_config(
            economics=EconomicsConfig(etf_ret=0.08)
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        etf_ret = ctx.etf_ret

        # then
        assert etf_ret == pytest.approx(0.08)

    def test_should_provide_feed_in_tariff_in_eur(self):
        """Should provide feed-in tariff converted to EUR/kWh."""
        # given
        config = _create_test_config(
            economics=EconomicsConfig(feed_in_tariff=8.0)  # ct/kWh
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        tariff = ctx.feed_in_tariff

        # then
        assert tariff == pytest.approx(0.08)  # EUR/kWh

    def test_should_provide_analysis_years(self):
        """Should provide access to analysis horizon in years."""
        # given
        config = _create_test_config(
            economics=EconomicsConfig(analysis_years=20)
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        years = ctx.analysis_years

        # then
        assert years == 20

    def test_should_provide_reinvest_savings_flag(self):
        """Should provide access to reinvest savings option."""
        # given
        config = _create_test_config(
            economics=EconomicsConfig(reinvest_savings=True)
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        reinvest = ctx.reinvest_savings

        # then
        assert reinvest is True

    def test_should_provide_total_consumption_from_results(self):
        """Should provide total consumption from first scenario."""
        # given
        config = _create_test_config()
        results = _create_test_results(total_consumption=4500.0)
        ctx = ReportContext(config=config, results=results)

        # when
        consumption = ctx.total_consumption

        # then
        assert consumption == pytest.approx(4500.0)

    def test_should_provide_scenarios_list(self):
        """Should provide access to scenario results list."""
        # given
        config = _create_test_config()
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        scenarios = ctx.scenarios

        # then
        assert len(scenarios) == 1
        assert scenarios[0].name == "Test Scenario"

    def test_should_provide_pv_generation_total(self):
        """Should provide total PV generation."""
        # given
        config = _create_test_config()
        results = _create_test_results(pv_generation_total=3500.0)
        ctx = ReportContext(config=config, results=results)

        # when
        pv_total = ctx.pv_generation_total

        # then
        assert pv_total == pytest.approx(3500.0)

    def test_should_provide_location_coordinates(self):
        """Should provide latitude and longitude."""
        # given
        config = _create_test_config(
            location=LocationConfig(lat=52.52, lon=13.405)
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when/then
        assert ctx.lat == pytest.approx(52.52)
        assert ctx.lon == pytest.approx(13.405)

    def test_should_provide_data_year(self):
        """Should provide PVGIS data year."""
        # given
        config = _create_test_config(
            pv_system=PVSystemConfig(
                data_year=2018,
                modules=[PVModule(id=0, name="Test", peak=1.0, azi=0, slope=30)],
            )
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        year = ctx.data_year

        # then
        assert year == 2018

    def test_should_provide_total_peak_power(self):
        """Should provide sum of all module peak powers."""
        # given
        config = _create_test_config(
            pv_system=PVSystemConfig(
                modules=[
                    PVModule(id=0, name="Module 1", peak=1.5, azi=0, slope=30),
                    PVModule(id=1, name="Module 2", peak=0.8, azi=90, slope=45),
                ],
            )
        )
        results = _create_test_results()
        ctx = ReportContext(config=config, results=results)

        # when
        total_kwp = ctx.total_peak_kwp

        # then
        assert total_kwp == pytest.approx(2.3)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

