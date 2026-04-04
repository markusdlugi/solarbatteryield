"""
Tests for the H0 standard load profile module.

The H0 profile module provides BDEW (Bundesverband der Energie- und Wasserwirtschaft)
standard load profiles for household electricity consumption, with differentiation
by day type (weekday, Saturday, Sunday/holiday) and season.
"""
import pytest
from datetime import date

from solarbatteryield.h0_profile import (
    DayType,
    Season,
    DayProfile,
    SeasonProfile,
    H0_WINTER,
    H0_SUMMER,
    H0_TRANSITION,
    H0_PROFILES,
    H0_BASE_ANNUAL_KWH,
    H0_AVERAGE_PROFILE,
    get_day_type,
    get_season,
    get_dynamization_factor,
    get_h0_load,
    is_holiday,
    get_simple_average_profile,
)


class TestDayTypeClassification:
    """Tests for day type classification based on weekday and holidays."""

    @pytest.mark.parametrize("weekday_date,day_name", [
        (date(2015, 1, 5), "Monday"),
        (date(2015, 1, 6), "Tuesday"),
        (date(2015, 1, 7), "Wednesday"),
        (date(2015, 1, 8), "Thursday"),
        (date(2015, 1, 9), "Friday"),
    ])
    def test_should_classify_weekday_as_weekday(self, weekday_date, day_name):
        """Should classify Monday through Friday as weekday."""
        # given
        # (parameters provided by decorator)

        # when
        day_type = get_day_type(weekday_date)

        # then
        assert day_type == DayType.WEEKDAY, f"{day_name} should be classified as WEEKDAY"

    def test_should_classify_saturday_as_saturday(self):
        """Should classify Saturday as Saturday."""
        # given
        saturday = date(2015, 1, 10)  # Saturday

        # when
        day_type = get_day_type(saturday)

        # then
        assert day_type == DayType.SATURDAY

    def test_should_classify_sunday_as_sunday(self):
        """Should classify Sunday as Sunday."""
        # given
        sunday = date(2015, 1, 11)  # Sunday

        # when
        day_type = get_day_type(sunday)

        # then
        assert day_type == DayType.SUNDAY

    def test_should_classify_new_years_day_as_sunday(self):
        """Should classify New Year's Day (German holiday) as Sunday."""
        # given
        new_years = date(2015, 1, 1)  # Thursday but holiday

        # when
        day_type = get_day_type(new_years)

        # then
        assert day_type == DayType.SUNDAY

    def test_should_classify_christmas_day_as_sunday(self):
        """Should classify Christmas Day (German holiday) as Sunday."""
        # given
        christmas = date(2015, 12, 25)  # Friday but holiday

        # when
        day_type = get_day_type(christmas)

        # then
        assert day_type == DayType.SUNDAY

    def test_should_classify_german_unity_day_as_sunday(self):
        """Should classify German Unity Day (Oct 3) as Sunday."""
        # given
        unity_day = date(2015, 10, 3)  # Saturday but also holiday

        # when
        day_type = get_day_type(unity_day)

        # then
        assert day_type == DayType.SUNDAY


class TestHolidayDetection:
    """Tests for German public holiday detection."""

    def test_should_detect_good_friday_as_holiday(self):
        """Should detect Good Friday as a German public holiday (variable date)."""
        # given
        good_friday_2015 = date(2015, 4, 3)  # Good Friday 2015

        # when
        result = is_holiday(good_friday_2015)

        # then
        assert result is True

    def test_should_detect_german_unity_day_as_holiday(self):
        """Should detect October 3rd (German Unity Day) as a public holiday."""
        # given
        unity_day = date(2015, 10, 3)

        # when
        result = is_holiday(unity_day)

        # then
        assert result is True

    def test_should_not_detect_regular_day_as_holiday(self):
        """Should not detect a regular working day as a holiday."""
        # given
        regular_day = date(2015, 3, 17)  # Regular Tuesday

        # when
        result = is_holiday(regular_day)

        # then
        assert result is False


class TestSeasonClassification:
    """Tests for season classification based on date."""

    @pytest.mark.parametrize("month,day,month_name", [
        (1, 15, "January"),
        (2, 15, "February"),
        (11, 15, "November"),
        (12, 15, "December"),
    ])
    def test_should_return_winter_for_winter_months(self, month, day, month_name):
        """Should classify winter months as winter."""
        # given
        # (parameters provided by decorator)

        # when
        season = get_season(month, day)

        # then
        assert season == Season.WINTER, f"{month_name} should be classified as WINTER"

    @pytest.mark.parametrize("month,day,month_name", [
        (7, 15, "July"),
        (8, 15, "August"),
    ])
    def test_should_return_summer_for_summer_months(self, month, day, month_name):
        """Should classify summer months as summer."""
        # given
        # (parameters provided by decorator)

        # when
        season = get_season(month, day)

        # then
        assert season == Season.SUMMER, f"{month_name} should be classified as SUMMER"

    @pytest.mark.parametrize("month,day,month_name", [
        (4, 15, "April"),
        (10, 15, "October"),
    ])
    def test_should_return_transition_for_transition_months(self, month, day, month_name):
        """Should classify transition months as transition."""
        # given
        # (parameters provided by decorator)

        # when
        season = get_season(month, day)

        # then
        assert season == Season.TRANSITION, f"{month_name} should be classified as TRANSITION"

    def test_should_handle_winter_to_transition_boundary(self):
        """Should correctly handle the March 20/21 boundary."""
        # given
        last_winter_day = date(2015, 3, 20)
        first_transition_day = date(2015, 3, 21)

        # when
        season_march_20 = get_season(last_winter_day.month, last_winter_day.day)
        season_march_21 = get_season(first_transition_day.month, first_transition_day.day)

        # then
        assert season_march_20 == Season.WINTER
        assert season_march_21 == Season.TRANSITION

    def test_should_handle_transition_to_summer_boundary(self):
        """Should correctly handle the May 14/15 boundary."""
        # given
        last_transition_day = date(2015, 5, 14)
        first_summer_day = date(2015, 5, 15)

        # when
        season_may_14 = get_season(last_transition_day.month, last_transition_day.day)
        season_may_15 = get_season(first_summer_day.month, first_summer_day.day)

        # then
        assert season_may_14 == Season.TRANSITION
        assert season_may_15 == Season.SUMMER


class TestDynamizationFactor:
    """Tests for the BDEW dynamization polynomial function."""

    def test_should_return_higher_factor_in_winter(self):
        """Should return higher dynamization factor in winter (start of year)."""
        # given
        winter_day = 15  # January 15
        summer_day = 180  # Late June

        # when
        winter_factor = get_dynamization_factor(winter_day)
        summer_factor = get_dynamization_factor(summer_day)

        # then
        assert winter_factor > summer_factor

    def test_should_return_approximately_1_2_at_year_start(self):
        """Should return approximately 1.2 at the beginning of the year."""
        # given
        day_of_year = 1

        # when
        factor = get_dynamization_factor(day_of_year)

        # then
        assert factor == pytest.approx(1.24, rel=0.05)

    def test_should_return_lower_factor_in_midsummer(self):
        """Should return lower dynamization factor around day 180."""
        # given
        midsummer_day = 180

        # when
        factor = get_dynamization_factor(midsummer_day)

        # then
        assert factor < 1.0
        assert factor > 0.7

    def test_should_be_symmetric_around_midsummer(self):
        """Should have roughly symmetric values around midsummer."""
        # given
        early_year = 50
        late_year = 310  # Roughly symmetric to day 50 around day 180

        # when
        early_factor = get_dynamization_factor(early_year)
        late_factor = get_dynamization_factor(late_year)

        # then
        assert early_factor == pytest.approx(late_factor, rel=0.15)


class TestH0ProfileData:
    """Tests verifying H0 profile data structure and integrity."""

    def test_should_have_three_season_profiles(self):
        """Should have profiles for winter, transition, and summer."""
        # given/when
        profile_count = len(H0_PROFILES)

        # then
        assert profile_count == 3

    def test_should_have_24_values_per_day_profile(self):
        """Should have exactly 24 hourly values in each day profile."""
        # given/when/then
        for season_profile in H0_PROFILES:
            assert len(season_profile.weekday.values) == 24
            assert len(season_profile.saturday.values) == 24
            assert len(season_profile.sunday.values) == 24

    def test_should_have_positive_values_in_all_profiles(self):
        """Should have all positive load values (consumption is never negative)."""
        # given/when/then
        for season_profile in H0_PROFILES:
            for day_type in DayType:
                profile = season_profile.get_profile(day_type)
                assert all(v > 0 for v in profile.values)

    def test_should_have_higher_evening_load(self):
        """Should have higher load values in evening hours than early morning."""
        # given
        profile = H0_WINTER.weekday
        early_morning_avg = sum(profile.values[2:5]) / 3  # Hours 2-4
        evening_avg = sum(profile.values[18:21]) / 3  # Hours 18-20

        # when/then
        assert evening_avg > early_morning_avg * 2


class TestDayProfile:
    """Tests for the DayProfile data class."""

    def test_should_reject_profile_with_wrong_length(self):
        """Should raise ValueError when profile doesn't have 24 values."""
        # given
        wrong_length_values = tuple([100.0] * 12)

        # when/then
        with pytest.raises(ValueError):
            DayProfile(wrong_length_values)

    def test_should_allow_indexing_by_hour(self):
        """Should allow accessing values by hour index."""
        # given
        profile = H0_WINTER.weekday

        # when
        hour_12_value = profile[12]

        # then
        assert hour_12_value == profile.values[12]

    def test_should_scale_values_correctly(self):
        """Should scale all values by the given factor."""
        # given
        profile = H0_WINTER.weekday
        scale_factor = 2.0

        # when
        scaled = profile.scaled(scale_factor)

        # then
        for original, scaled_val in zip(profile.values, scaled.values):
            assert scaled_val == pytest.approx(original * scale_factor)


class TestH0LoadCalculation:
    """Tests for H0 load value calculation."""

    def test_should_scale_load_with_annual_consumption(self):
        """Should scale load proportionally with annual consumption."""
        # given
        test_date = date(2015, 6, 15)
        annual_kwh_low = 2000
        annual_kwh_high = 4000

        # when
        load_low = get_h0_load(12, test_date, annual_kwh_low)
        load_high = get_h0_load(12, test_date, annual_kwh_high)

        # then
        assert load_high == pytest.approx(load_low * 2, rel=0.01)

    def test_should_return_higher_load_in_winter(self):
        """Should return higher load in winter due to dynamization."""
        # given
        annual_kwh = 3000
        # Use weekday for both to isolate seasonal effect
        # Find Wednesdays in each month
        winter_wed = date(2015, 1, 14)  # Wednesday
        summer_wed = date(2015, 7, 15)  # Wednesday

        # when
        winter_load = get_h0_load(12, winter_wed, annual_kwh)
        summer_load = get_h0_load(12, summer_wed, annual_kwh)

        # then
        assert winter_load > summer_load

    def test_should_sum_to_approximately_annual_consumption(self):
        """Should sum to approximately the target annual consumption over a year."""
        # given
        annual_kwh = 3000
        start_date = date(2015, 1, 1)
        total_load = 0.0

        # when
        for day_offset in range(365):
            current_date = date.fromordinal(start_date.toordinal() + day_offset)
            for hour in range(24):
                total_load += get_h0_load(hour, current_date, annual_kwh)

        # then
        assert total_load == pytest.approx(annual_kwh, rel=0.02)


class TestH0BaseAnnualKwh:
    """Tests for the pre-calculated base annual consumption."""

    def test_should_have_positive_base_annual_kwh(self):
        """Should have a positive base annual consumption value."""
        # given/when
        base_kwh = H0_BASE_ANNUAL_KWH

        # then
        assert base_kwh > 0

    def test_should_have_reasonable_base_value(self):
        """Should have a base annual value in the expected range (around 1000 kWh)."""
        # given/when
        base_kwh = H0_BASE_ANNUAL_KWH

        # then
        # The base profile is normalized to approximately 1000 kWh/year
        assert 900 < base_kwh < 1200


class TestH0AverageProfile:
    """Tests for the average profile calculation."""

    def test_should_have_24_hourly_values(self):
        """Should have 24 hourly values in the average profile."""
        # given/when
        profile = H0_AVERAGE_PROFILE

        # then
        assert len(profile) == 24

    def test_should_have_positive_values(self):
        """Should have all positive values in the average profile."""
        # given/when
        profile = H0_AVERAGE_PROFILE

        # then
        assert all(v > 0 for v in profile)

    def test_should_match_simple_average_calculation(self):
        """Should match the get_simple_average_profile function output."""
        # given/when
        calculated = get_simple_average_profile()

        # then
        assert H0_AVERAGE_PROFILE == calculated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

