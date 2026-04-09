"""
Tests for the sidebar profile_io module.

Tests CSV template generation and parsing functionality for expert mode
yearly consumption profiles.
"""
import io
import pytest

from solarbatteryield.sidebar.profile_io import (
    is_leap_year,
    get_hours_in_year,
    generate_yearly_template_csv,
    parse_yearly_profile_csv,
    calculate_profile_stats,
)


class TestLeapYearDetection:
    """Tests for leap year detection."""

    @pytest.mark.parametrize("year,expected", [
        (2000, True),   # Divisible by 400
        (2004, True),   # Divisible by 4
        (2015, False),  # Not divisible by 4
        (2016, True),   # Divisible by 4
        (1900, False),  # Divisible by 100 but not 400
        (2100, False),  # Divisible by 100 but not 400
    ])
    def test_should_correctly_identify_leap_years(self, year, expected):
        """Should correctly identify leap years according to Gregorian calendar rules."""
        # given/when
        result = is_leap_year(year)

        # then
        assert result == expected


class TestHoursInYear:
    """Tests for hours in year calculation."""

    def test_should_return_8760_for_normal_year(self):
        """Should return 8760 hours for a non-leap year."""
        # given
        year = 2015

        # when
        hours = get_hours_in_year(year)

        # then
        assert hours == 8760

    def test_should_return_8784_for_leap_year(self):
        """Should return 8784 hours for a leap year."""
        # given
        year = 2016

        # when
        hours = get_hours_in_year(year)

        # then
        assert hours == 8784


class TestTemplateGeneration:
    """Tests for CSV template generation."""

    def test_should_generate_correct_header(self):
        """Should generate CSV with Time and Power columns."""
        # given
        year = 2015

        # when
        csv_content = generate_yearly_template_csv(year)

        # then
        lines = csv_content.strip().split("\n")
        assert lines[0] == "Time;Power(W)"

    def test_should_generate_correct_number_of_rows_for_normal_year(self):
        """Should generate 8760 data rows for a non-leap year."""
        # given
        year = 2015

        # when
        csv_content = generate_yearly_template_csv(year)

        # then
        lines = csv_content.strip().split("\n")
        # 1 header + 8760 data rows
        assert len(lines) == 8761

    def test_should_generate_correct_number_of_rows_for_leap_year(self):
        """Should generate 8784 data rows for a leap year."""
        # given
        year = 2016

        # when
        csv_content = generate_yearly_template_csv(year)

        # then
        lines = csv_content.strip().split("\n")
        # 1 header + 8784 data rows
        assert len(lines) == 8785

    def test_should_start_with_jan_1_midnight(self):
        """Should start timestamps at January 1st, 00:00."""
        # given
        year = 2015

        # when
        csv_content = generate_yearly_template_csv(year)

        # then
        lines = csv_content.strip().split("\n")
        first_data_line = lines[1]
        assert first_data_line.startswith("2015-01-01 00:00")


class TestCsvParsing:
    """Tests for CSV parsing."""

    def _create_csv_file(self, content: str):
        """Helper to create a file-like object from CSV content."""
        return io.StringIO(content)

    def test_should_parse_valid_csv(self):
        """Should successfully parse a valid CSV with power values."""
        # given
        csv_content = "Time;Power(W)\n2015-01-01 00:00;100\n2015-01-01 01:00;200\n"
        # Create a minimal valid CSV (we'll mock the year check)
        num_hours = 8760
        lines = ["Time;Power(W)"] + [f"2015-01-01 {h:02d}:00;{h * 10}" for h in range(num_hours)]
        csv_content = "\n".join(lines)
        uploaded_file = self._create_csv_file(csv_content)

        # when
        profile_data, error = parse_yearly_profile_csv(uploaded_file, 2015)

        # then
        assert error is None
        assert profile_data is not None
        assert len(profile_data) == 8760
        assert profile_data[0] == 0  # First hour: 0 * 10
        assert profile_data[1] == 10  # Second hour: 1 * 10

    def test_should_reject_csv_with_wrong_row_count(self):
        """Should reject CSV with incorrect number of rows."""
        # given
        csv_content = "Time;Power(W)\n2015-01-01 00:00;100\n2015-01-01 01:00;200\n"
        uploaded_file = self._create_csv_file(csv_content)

        # when
        profile_data, error = parse_yearly_profile_csv(uploaded_file, 2015)

        # then
        assert profile_data is None
        assert error is not None
        assert "8760" in error  # Should mention expected row count

    def test_should_reject_csv_with_missing_columns(self):
        """Should reject CSV with only one column."""
        # given
        csv_content = "Time\n2015-01-01 00:00\n"
        uploaded_file = self._create_csv_file(csv_content)

        # when
        profile_data, error = parse_yearly_profile_csv(uploaded_file, 2015)

        # then
        assert profile_data is None
        assert error is not None
        assert "2 Spalten" in error

    def test_should_reject_csv_with_negative_values(self):
        """Should reject CSV containing negative power values."""
        # given
        num_hours = 8760
        lines = ["Time;Power(W)"] + [f"2015-01-01 {h % 24:02d}:00;{-10 if h == 5 else 100}" for h in range(num_hours)]
        csv_content = "\n".join(lines)
        uploaded_file = self._create_csv_file(csv_content)

        # when
        profile_data, error = parse_yearly_profile_csv(uploaded_file, 2015)

        # then
        assert profile_data is None
        assert error is not None
        assert "negative" in error.lower()

    def test_should_reject_empty_csv(self):
        """Should reject empty CSV file."""
        # given
        csv_content = ""
        uploaded_file = self._create_csv_file(csv_content)

        # when
        profile_data, error = parse_yearly_profile_csv(uploaded_file, 2015)

        # then
        assert profile_data is None
        assert error is not None
        assert "leer" in error.lower()


class TestProfileStats:
    """Tests for profile statistics calculation."""

    def test_should_calculate_correct_total_kwh(self):
        """Should calculate total consumption in kWh from Watt values."""
        # given
        profile_data = [1000.0] * 100  # 1000W for 100 hours = 100 kWh

        # when
        stats = calculate_profile_stats(profile_data)

        # then
        assert stats["total_kwh"] == pytest.approx(100.0)

    def test_should_calculate_correct_average(self):
        """Should calculate average power correctly."""
        # given
        profile_data = [100.0, 200.0, 300.0]

        # when
        stats = calculate_profile_stats(profile_data)

        # then
        assert stats["avg_w"] == pytest.approx(200.0)

    def test_should_find_min_and_max(self):
        """Should correctly identify minimum and maximum power values."""
        # given
        profile_data = [50.0, 100.0, 500.0, 200.0]

        # when
        stats = calculate_profile_stats(profile_data)

        # then
        assert stats["min_w"] == pytest.approx(50.0)
        assert stats["max_w"] == pytest.approx(500.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

