"""
Tests for utility functions in the utils module.

Only the calc_amortization_with_price_increase function requires testing
as the other functions are simple formatting utilities.
"""
import pytest

from solarbatteryield.utils import calc_amortization_with_price_increase


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

