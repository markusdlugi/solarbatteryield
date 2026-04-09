"""
Tests for the report chart_config module.

Tests the shared Altair chart configuration helpers.
"""
import pytest

from solarbatteryield.report.chart_config import GERMAN_LOCALE, configure_german_locale


class TestGermanLocale:
    """Tests for German locale configuration."""

    def test_should_use_comma_as_decimal_separator(self):
        """Should configure comma as decimal separator for German locale."""
        # given/when
        locale = GERMAN_LOCALE

        # then
        assert locale["number"]["decimal"] == ","

    def test_should_use_period_as_thousands_separator(self):
        """Should configure period as thousands separator for German locale."""
        # given/when
        locale = GERMAN_LOCALE

        # then
        assert locale["number"]["thousands"] == "."

    def test_should_use_groups_of_three(self):
        """Should configure grouping of three digits."""
        # given/when
        locale = GERMAN_LOCALE

        # then
        assert locale["number"]["grouping"] == [3]

    def test_should_have_euro_currency_suffix(self):
        """Should configure Euro as currency with suffix format."""
        # given/when
        locale = GERMAN_LOCALE

        # then
        assert locale["number"]["currency"] == ["", " €"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

