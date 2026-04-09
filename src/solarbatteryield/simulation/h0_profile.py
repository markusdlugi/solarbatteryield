"""
BDEW H0 Standard Load Profile for household electricity consumption.

This module provides the BDEW H0 standard load profile data with differentiation
by day type (weekday, Saturday, Sunday/holiday) and season.

Data source: VDEW/BDEW (Bundesverband der Energie- und Wasserwirtschaft)
Original publication: "Repräsentative VDEW-Lastprofile" (1999)
https://www.bdew.de/energie/standardlastprofile-strom/

The 15-minute interval data is aggregated to hourly values using the mean of
each hour's four quarter-hour values. Timestamps in the source data represent
the END of each interval (e.g., 00:15 = interval 00:00-00:15).

Reference: "Anwendung der Repräsentativen VDEW-Lastprofile - Step by Step"
https://www.bdew.de/media/documents/2000131_Anwendung-repraesentativen_Lastprofile-Step-by-step.pdf

The profile values are in Watts and represent a typical household consumption pattern.
Values are normalized to approximately 1000 kWh/year as a base that gets scaled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from functools import lru_cache
from typing import NamedTuple

import holidays


class DayType(Enum):
    """Day type classification for load profiles."""
    WEEKDAY = "weekday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"  # Also used for holidays


class Season(Enum):
    """Season classification for load profiles."""
    WINTER = "winter"      # 11/01 - 03/20
    TRANSITION = "transition"  # 03/21 - 05/14 AND 09/15 - 10/31
    SUMMER = "summer"      # 05/15 - 09/14


class SeasonBoundary(NamedTuple):
    """Defines the first day a season ends (exclusive)."""
    month: int
    day: int
    season: Season


# Season boundaries: each entry defines when the season ENDS
# The "till" dates from BDEW specify the first day the season no longer applies
# Note: BDEW defines 5 periods but only 3 distinct profiles:
#   - Winter profile: 11/01 - 03/20
#   - Transition profile (spring/autumn): 03/21 - 05/14 AND 09/15 - 10/31
#   - Summer profile: 05/15 - 09/14
SEASON_BOUNDARIES: list[SeasonBoundary] = [
    SeasonBoundary(3, 21, Season.WINTER),       # Winter until 03/20
    SeasonBoundary(5, 15, Season.TRANSITION),   # Transition (spring) 03/21 - 05/14
    SeasonBoundary(9, 15, Season.SUMMER),       # Summer 05/15 - 09/14
    SeasonBoundary(11, 1, Season.TRANSITION),   # Transition (autumn) 09/15 - 10/31
    SeasonBoundary(12, 32, Season.WINTER),      # Winter 11/01 - 12/31
]


@dataclass(frozen=True)
class DayProfile:
    """24-hour load profile for a specific day type (in Watts)."""
    values: tuple[float, ...]
    
    def __post_init__(self) -> None:
        if len(self.values) != 24:
            raise ValueError(f"Profile must have 24 hourly values, got {len(self.values)}")
    
    def __getitem__(self, hour: int) -> float:
        return self.values[hour]
    
    def scaled(self, factor: float) -> "DayProfile":
        """Return a new profile scaled by the given factor."""
        return DayProfile(tuple(v * factor for v in self.values))


@dataclass(frozen=True)
class SeasonProfile:
    """Load profiles for all day types within a season."""
    season: Season
    weekday: DayProfile
    saturday: DayProfile
    sunday: DayProfile
    
    def get_profile(self, day_type: DayType) -> DayProfile:
        """Get the profile for a specific day type."""
        if day_type == DayType.WEEKDAY:
            return self.weekday
        elif day_type == DayType.SATURDAY:
            return self.saturday
        else:
            return self.sunday


# ─── BDEW H0 Profile Data ────────────────────────────────────────────────────
# Values in Watts, normalized to approximately 1000 kWh/year base
# Source: VDEW/BDEW "Repräsentative Profile" Excel file (1999)
# Hourly values are the mean of each hour's four 15-minute interval values.

H0_WINTER = SeasonProfile(
    season=Season.WINTER,
    weekday=DayProfile((
        58.3, 43.125, 39.55, 38.5, 39.125, 46.875,
        90.075, 129.4, 133.5, 123.2, 116.225, 118.325,
        130.7, 129.475, 115.35, 104.825, 105.225, 128.65,
        166.175, 187.05, 168.225, 140.975, 116.675, 86.4,
    )),
    saturday=DayProfile((
        67.05, 52.9, 42.1, 39.7, 38.475, 40.075,
        53.1, 81.95, 119.7, 141.7, 147.85, 155.0,
        166.6, 165.825, 153.45, 143.775, 144.75, 180.5,
        209.4, 210.125, 171.95, 134.1, 122.5, 103.925,
    )),
    sunday=DayProfile((
        78.175, 56.275, 45.075, 41.15, 38.725, 38.625,
        40.95, 50.0, 88.525, 138.5, 174.175, 202.775,
        206.7, 173.025, 136.125, 116.6, 106.7, 125.7,
        156.4, 176.275, 160.125, 135.525, 114.75, 84.625,
    )),
)

H0_TRANSITION = SeasonProfile(
    season=Season.TRANSITION,
    weekday=DayProfile((
        66.6, 49.175, 44.275, 43.1, 44.05, 52.625,
        92.925, 129.725, 137.475, 135.95, 132.05, 133.25,
        149.6, 145.65, 126.775, 113.4, 106.15, 116.325,
        144.85, 171.925, 168.05, 155.95, 135.7, 100.25,
    )),
    saturday=DayProfile((
        73.15, 56.3, 46.45, 43.775, 43.15, 45.15,
        58.575, 93.25, 129.675, 150.375, 163.275, 171.825,
        181.375, 177.45, 161.275, 148.675, 146.525, 159.375,
        183.275, 198.05, 180.375, 147.325, 138.575, 116.5,
    )),
    sunday=DayProfile((
        84.275, 62.2, 48.875, 44.275, 43.175, 43.275,
        45.725, 65.55, 111.225, 159.525, 185.075, 205.175,
        207.8, 168.625, 136.25, 121.025, 107.3, 111.75,
        137.55, 160.925, 154.75, 143.925, 127.625, 93.975,
    )),
)

H0_SUMMER = SeasonProfile(
    season=Season.SUMMER,
    weekday=DayProfile((
        73.6, 54.825, 49.775, 46.875, 48.8, 59.25,
        97.9, 129.725, 141.625, 144.075, 139.25, 141.95,
        157.8, 152.7, 131.775, 118.775, 114.775, 122.5,
        142.175, 165.15, 166.575, 157.525, 144.5, 112.075,
    )),
    saturday=DayProfile((
        83.0, 64.325, 52.325, 50.025, 50.5, 51.65,
        63.7, 93.1, 128.375, 155.75, 164.85, 171.125,
        182.125, 175.975, 157.175, 148.375, 144.825, 148.95,
        166.5, 180.375, 172.9, 153.825, 148.6, 124.65,
    )),
    sunday=DayProfile((
        89.6, 66.65, 54.475, 50.6, 49.975, 48.775,
        51.325, 69.5, 112.45, 160.25, 186.6, 205.725,
        209.45, 175.375, 144.075, 124.375, 108.375, 109.55,
        126.65, 152.025, 159.425, 150.5, 140.2, 108.075,
    )),
)

# All H0 profiles
H0_PROFILES: frozenset[SeasonProfile] = frozenset({H0_WINTER, H0_TRANSITION, H0_SUMMER})

# Lookup by season (built once at module load)
_PROFILE_BY_SEASON: dict[Season, SeasonProfile] = {p.season: p for p in H0_PROFILES}

# ─── German Public Holidays ──────────────────────────────────────────────────

@lru_cache(maxsize=32)
def _get_german_holidays(year: int) -> holidays.Germany:
    """Get German holidays for a specific year (cached)."""
    return holidays.Germany(years=year)


def is_holiday(d: date) -> bool:
    """Check if a date is a German public holiday."""
    return d in _get_german_holidays(d.year)


# ─── BDEW Dynamization Function ──────────────────────────────────────────────
# This polynomial function adjusts the load profile based on the day of year
# to create smooth seasonal transitions. Higher values in winter, lower in summer.
# Source: VDEW/BDEW "Haushalt-Lastprofil.xls" - Dynamischer Jahresverlauf sheet

# Polynomial coefficients for the dynamization function
# y = a4*d^4 + a3*d^3 + a2*d^2 + a1*d + a0, where d = day of year
_DYN_A4 = -0.000000000392
_DYN_A3 = 0.00000032
_DYN_A2 = -0.0000702
_DYN_A1 = 0.0021
_DYN_A0 = 1.24


@lru_cache(maxsize=366)
def get_dynamization_factor(day_of_year: int) -> float:
    """
    Calculate the BDEW dynamization factor for a given day of year.
    
    This polynomial function creates smooth seasonal variation:
    - Higher values (~1.2) in winter (around day 1 and 365)
    - Lower values (~0.8) in summer (around day 180)
    
    Args:
        day_of_year: Day of the year (1-365/366)
    
    Returns:
        Dynamization factor to multiply with the base load (cached)
    """
    d = day_of_year
    return (
        _DYN_A4 * d**4 +
        _DYN_A3 * d**3 +
        _DYN_A2 * d**2 +
        _DYN_A1 * d +
        _DYN_A0
    )


def get_day_type(d: date) -> DayType:
    """
    Determine the day type for load profile selection.
    
    Returns:
        DayType.SUNDAY for Sundays and public holidays
        DayType.SATURDAY for Saturdays
        DayType.WEEKDAY for Monday through Friday (non-holidays)
    """
    # Check for Sunday or holiday first
    if d.weekday() == 6 or is_holiday(d):
        return DayType.SUNDAY
    # Check for Saturday
    if d.weekday() == 5:
        return DayType.SATURDAY
    # Otherwise it's a weekday
    return DayType.WEEKDAY


def get_season(month: int, day: int) -> Season:
    """
    Determine the season for a given date.
    
    Args:
        month: Month (1-12)
        day: Day of month (1-31)
    
    Returns:
        Season enum value
    """
    for boundary in SEASON_BOUNDARIES:
        if month < boundary.month or (month == boundary.month and day < boundary.day):
            return boundary.season
    return Season.WINTER  # Fallback (should not happen with proper boundaries)


def get_h0_load(hour: int, d: date, annual_kwh: float) -> float:
    """
    Get the H0 load for a specific hour and date, scaled to annual consumption.
    
    This applies:
    1. Season-specific profile (winter/transition/summer)
    2. Day-type profile (weekday/saturday/sunday)
    3. BDEW dynamization factor for smooth seasonal variation
    4. Scaling to target annual consumption
    
    Args:
        hour: Hour of day (0-23)
        d: Date for determining season and day type
        annual_kwh: Target annual consumption in kWh
    
    Returns:
        Load in kWh for the hour
    """
    season = get_season(d.month, d.day)
    day_type = get_day_type(d)
    
    profile = _PROFILE_BY_SEASON[season].get_profile(day_type)
    
    # Get base load from profile (in Watts)
    base_load_w = profile[hour]
    
    # Apply dynamization factor based on day of year
    day_of_year = d.timetuple().tm_yday
    dyn_factor = get_dynamization_factor(day_of_year)
    dynamized_load_w = base_load_w * dyn_factor
    
    # Scale from base profile to target annual consumption
    scale_factor = annual_kwh / H0_BASE_ANNUAL_KWH
    
    # Convert from Watts to kWh (Watts / 1000 = kW, × 1 hour = kWh)
    return dynamized_load_w / 1000.0 * scale_factor


def calculate_h0_base_annual_kwh() -> float:
    """
    Calculate the base annual consumption of the H0 profile in kWh.
    
    This performs a full year simulation accounting for:
    - Season-specific profiles
    - Day-type distribution (weekdays, Saturdays, Sundays/holidays)
    - BDEW dynamization factor
    """
    # Use a reference year for calculation
    reference_year = 2015
    total_kwh = 0.0
    
    start_date = date(reference_year, 1, 1)
    days_in_year = 366 if reference_year % 4 == 0 else 365
    
    for day_offset in range(days_in_year):
        current_date = date.fromordinal(start_date.toordinal() + day_offset)
        day_of_year = current_date.timetuple().tm_yday
        
        season = get_season(current_date.month, current_date.day)
        day_type = get_day_type(current_date)
        profile = _PROFILE_BY_SEASON[season].get_profile(day_type)
        
        # Apply dynamization factor
        dyn_factor = get_dynamization_factor(day_of_year)
        
        # Sum hourly consumption for this day
        daily_kwh = sum(profile.values) / 1000.0 * dyn_factor
        total_kwh += daily_kwh
    
    return total_kwh


# Pre-calculated base annual consumption for the H0 profile
# This is used for scaling to user's target annual consumption
# Calculated with dynamization factor applied
H0_BASE_ANNUAL_KWH: float = calculate_h0_base_annual_kwh()


def get_simple_average_profile() -> list[float]:
    """
    Get a simple daily average profile (for display purposes).

    Returns average across all seasons and day types in Watts.
    """
    hourly_totals = [0.0] * 24
    count = 0

    for season_profile in H0_PROFILES:
        for day_type in DayType:
            profile = season_profile.get_profile(day_type)
            for hour in range(24):
                hourly_totals[hour] += profile[hour]
            count += 1

    return [total / count for total in hourly_totals]


# Default average profile for display in simple mode (in Watts)
H0_AVERAGE_PROFILE: list[float] = get_simple_average_profile()

