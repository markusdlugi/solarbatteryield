"""
Tests for utility functions in the utils module.

Tests calc_amortization_with_price_increase and build_yearly_data
(including reinvest savings feature).
"""
import pytest

from solarbatteryield.utils import calc_amortization_with_price_increase, build_yearly_data


# ─── Common parameters for build_yearly_data tests ─────────────────────────────

_BASE_PARAMS = dict(
    saved_kwh=1000.0,
    feed_in_kwh=0.0,
    feed_in_tariff=0.0,
    cost=1000.0,
    e_price=0.30,
    e_inc=0.0,
    etf_ret=0.07,
    years=10,
)


class TestCalcAmortizationWithPriceIncrease:
    """Tests for amortization calculation with price increases."""

    def test_should_return_infinity_for_zero_savings(self):
        """Should return infinity when there are no savings."""
        # given
        invest = 1000.0
        d_kwh = 0.0
        d_feed_in = 0.0

        # when
        result = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=d_feed_in,
            e_price=0.30,
            e_inc=0.03,
            feed_in_tariff=0.08,
        )

        # then
        assert result == float("inf")

    def test_should_return_infinity_for_negative_savings(self):
        """Should return infinity when savings are negative."""
        # given
        invest = 1000.0
        d_kwh = -100.0
        d_feed_in = -50.0

        # when
        result = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=d_feed_in,
            e_price=0.30,
            e_inc=0.03,
            feed_in_tariff=0.08,
        )

        # then
        assert result == float("inf")

    def test_should_calculate_simple_payback_without_price_increase(self):
        """Should calculate correct payback period with zero price increase."""
        # given
        invest = 1000.0
        d_kwh = 500.0  # 500 kWh/year saved
        e_price = 0.40  # 0.40 EUR/kWh -> 200 EUR/year savings
        e_inc = 0.0  # No price increase

        # when
        result = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=0.0,
            e_price=e_price,
            e_inc=e_inc,
            feed_in_tariff=0.0,
        )

        # then
        # 1000 EUR / 200 EUR/year = 5 years
        assert result == pytest.approx(5.0)

    def test_should_include_feed_in_revenue_in_payback(self):
        """Should include feed-in revenue when calculating payback."""
        # given
        invest = 1000.0
        d_kwh = 0.0  # No savings from self-consumption
        d_feed_in = 1000.0  # 1000 kWh/year fed in
        feed_in_tariff = 0.10  # 0.10 EUR/kWh -> 100 EUR/year

        # when
        result = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=d_feed_in,
            e_price=0.30,
            e_inc=0.0,
            feed_in_tariff=feed_in_tariff,
        )

        # then
        # 1000 EUR / 100 EUR/year = 10 years
        assert result == pytest.approx(10.0)

    def test_should_reduce_payback_with_price_increase(self):
        """Should result in shorter payback when prices increase."""
        # given
        invest = 1000.0
        d_kwh = 500.0
        e_price = 0.30

        # when
        result_no_increase = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=0.0,
            e_price=e_price,
            e_inc=0.0,
            feed_in_tariff=0.0,
        )
        result_with_increase = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=0.0,
            e_price=e_price,
            e_inc=0.05,  # 5% annual increase
            feed_in_tariff=0.0,
        )

        # then
        assert result_with_increase < result_no_increase

    def test_should_return_decimal_precision(self):
        """Should return payback period with decimal precision."""
        # given
        invest = 1000.0
        d_kwh = 333.33  # Results in non-integer payback
        e_price = 0.30  # ~100 EUR/year -> ~10 years

        # when
        result = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=0.0,
            e_price=e_price,
            e_inc=0.0,
            feed_in_tariff=0.0,
        )

        # then
        # Should not be a whole number
        assert result != int(result)
        assert result == pytest.approx(10.0, rel=0.01)

    def test_should_return_infinity_when_payback_exceeds_max_years(self):
        """Should return infinity when payback exceeds maximum years."""
        # given
        invest = 100000.0  # Very high investment
        d_kwh = 100.0  # Low savings
        e_price = 0.30  # 30 EUR/year savings

        # when
        result = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=0.0,
            e_price=e_price,
            e_inc=0.0,
            feed_in_tariff=0.0,
            max_years=50,
        )

        # then
        # 100000 / 30 = 3333 years > 50 max_years
        assert result == float("inf")

    def test_should_combine_savings_and_feed_in(self):
        """Should correctly combine self-consumption savings and feed-in revenue."""
        # given
        invest = 1000.0
        d_kwh = 250.0  # 250 kWh saved
        d_feed_in = 500.0  # 500 kWh fed in
        e_price = 0.40  # 250 * 0.40 = 100 EUR from savings
        feed_in_tariff = 0.10  # 500 * 0.10 = 50 EUR from feed-in
        # Total: 150 EUR/year

        # when
        result = calc_amortization_with_price_increase(
            invest=invest,
            d_kwh=d_kwh,
            d_feed_in=d_feed_in,
            e_price=e_price,
            e_inc=0.0,
            feed_in_tariff=feed_in_tariff,
        )

        # then
        # 1000 / 150 = 6.67 years
        assert result == pytest.approx(6.67, rel=0.01)


class TestBuildYearlyDataWithoutReinvest:
    """Tests for build_yearly_data baseline behavior (reinvest disabled)."""

    def test_should_not_include_reinvest_column_when_disabled(self):
        """Should not contain a Reinvest-Ertrag column when reinvest_savings is False."""
        # given / when
        df = build_yearly_data(**_BASE_PARAMS, reinvest_savings=False)

        # then
        assert "Reinvest-Ertrag (EUR)" not in df.columns

    def test_should_have_correct_number_of_rows(self):
        """Should return one row per year."""
        # given / when
        df = build_yearly_data(**_BASE_PARAMS)

        # then
        assert len(df) == _BASE_PARAMS["years"]

    def test_should_calculate_pv_netto_as_cumulated_minus_cost(self):
        """Should compute PV netto = cumulated savings - investment cost."""
        # given
        # 1000 kWh * 0.30 EUR/kWh = 300 EUR/year, no price increase
        # After 5 years: 1500 cumulated - 1000 cost = 500 net

        # when
        df = build_yearly_data(**_BASE_PARAMS)

        # then
        row_5 = df[df["Jahr"] == 5].iloc[0]
        assert row_5["PV kumuliert (EUR)"] == pytest.approx(1500.0)
        assert row_5["PV netto (EUR)"] == pytest.approx(500.0)

    def test_should_calculate_etf_with_compound_interest(self):
        """Should compute ETF value using compound interest on initial investment."""
        # given
        cost = 1000.0
        etf_ret = 0.07

        # when
        df = build_yearly_data(**_BASE_PARAMS)

        # then
        row_1 = df[df["Jahr"] == 1].iloc[0]
        assert row_1["ETF Wert (EUR)"] == pytest.approx(cost * 1.07)
        assert row_1["ETF netto (EUR)"] == pytest.approx(cost * 0.07)

    def test_should_apply_electricity_price_increase(self):
        """Should increase yearly PV savings when electricity price rises."""
        # given
        params = {**_BASE_PARAMS, "e_inc": 0.10}  # 10% annual increase

        # when
        df = build_yearly_data(**params)

        # then – year 2 savings should be 10% higher than year 1
        year_1_cum = df[df["Jahr"] == 1].iloc[0]["PV kumuliert (EUR)"]
        year_2_cum = df[df["Jahr"] == 2].iloc[0]["PV kumuliert (EUR)"]
        year_2_savings = year_2_cum - year_1_cum
        assert year_2_savings > year_1_cum, "Year 2 savings should exceed year 1 due to price increase"


class TestBuildYearlyDataWithReinvest:
    """Tests for build_yearly_data with reinvest savings enabled."""

    def test_should_include_reinvest_column_when_enabled(self):
        """Should contain a Reinvest-Ertrag column when reinvest_savings is True."""
        # given / when
        df = build_yearly_data(**_BASE_PARAMS, reinvest_savings=True)

        # then
        assert "Reinvest-Ertrag (EUR)" in df.columns

    def test_should_have_positive_reinvest_returns_with_positive_etf(self):
        """Should produce positive reinvest returns when ETF return is positive."""
        # given / when
        df = build_yearly_data(**_BASE_PARAMS, reinvest_savings=True)

        # then
        for _, row in df.iterrows():
            assert row["Reinvest-Ertrag (EUR)"] > 0, (
                f"Year {int(row['Jahr'])}: reinvest return should be positive"
            )

    def test_should_increase_pv_netto_compared_to_without_reinvest(self):
        """Should produce higher PV netto when reinvesting vs not reinvesting."""
        # given / when
        df_without = build_yearly_data(**_BASE_PARAMS, reinvest_savings=False)
        df_with = build_yearly_data(**_BASE_PARAMS, reinvest_savings=True)

        # then
        for y in range(len(df_without)):
            pv_net_without = df_without.iloc[y]["PV netto (EUR)"]
            pv_net_with = df_with.iloc[y]["PV netto (EUR)"]
            assert pv_net_with > pv_net_without, (
                f"Year {y + 1}: PV netto with reinvest ({pv_net_with:.0f}) "
                f"should exceed without ({pv_net_without:.0f})"
            )

    def test_should_compute_pv_netto_as_cumulated_plus_reinvest_minus_cost(self):
        """Should satisfy PV netto = PV kumuliert + Reinvest-Ertrag - cost."""
        # given
        cost = _BASE_PARAMS["cost"]

        # when
        df = build_yearly_data(**_BASE_PARAMS, reinvest_savings=True)

        # then
        for _, row in df.iterrows():
            expected = row["PV kumuliert (EUR)"] + row["Reinvest-Ertrag (EUR)"] - cost
            assert row["PV netto (EUR)"] == pytest.approx(expected, abs=0.01), (
                f"Year {int(row['Jahr'])}: PV netto should equal cumulated + reinvest - cost"
            )

    def test_should_use_constant_monthly_rate_regardless_of_price_increase(self):
        """Should use the same monthly savings rate even when electricity prices rise."""
        # given – same savings but different price increase rates
        params_no_inc = {**_BASE_PARAMS, "e_inc": 0.0}
        params_with_inc = {**_BASE_PARAMS, "e_inc": 0.05}

        # when
        df_no_inc = build_yearly_data(**params_no_inc, reinvest_savings=True)
        df_with_inc = build_yearly_data(**params_with_inc, reinvest_savings=True)

        # then – reinvest returns should be identical (constant monthly rate from year 1)
        for y in range(len(df_no_inc)):
            assert df_no_inc.iloc[y]["Reinvest-Ertrag (EUR)"] == pytest.approx(
                df_with_inc.iloc[y]["Reinvest-Ertrag (EUR)"], rel=1e-9
            ), f"Year {y + 1}: reinvest returns should be identical regardless of e_inc"

    def test_should_produce_zero_reinvest_returns_with_zero_etf_return(self):
        """Should produce zero reinvest returns when ETF return rate is 0%."""
        # given
        params = {**_BASE_PARAMS, "etf_ret": 0.0}

        # when
        df = build_yearly_data(**params, reinvest_savings=True)

        # then
        for _, row in df.iterrows():
            assert row["Reinvest-Ertrag (EUR)"] == pytest.approx(0.0, abs=0.01)

    def test_should_grow_reinvest_returns_over_time(self):
        """Should produce increasing reinvest returns each year (compound effect)."""
        # given / when
        df = build_yearly_data(**_BASE_PARAMS, reinvest_savings=True)

        # then
        prev = 0.0
        for _, row in df.iterrows():
            assert row["Reinvest-Ertrag (EUR)"] > prev, (
                f"Year {int(row['Jahr'])}: reinvest return should grow over time"
            )
            prev = row["Reinvest-Ertrag (EUR)"]

    def test_should_improve_pv_vs_etf_comparison_with_reinvest(self):
        """Should improve the PV - ETF difference when reinvesting."""
        # given / when
        df_without = build_yearly_data(**_BASE_PARAMS, reinvest_savings=False)
        df_with = build_yearly_data(**_BASE_PARAMS, reinvest_savings=True)

        # then
        final_without = df_without.iloc[-1]["PV - ETF (EUR)"]
        final_with = df_with.iloc[-1]["PV - ETF (EUR)"]
        assert final_with > final_without


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

