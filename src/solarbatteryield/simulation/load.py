"""
Load calculation and flexible load pool management.

Extracted from _core.py to keep the simulation loop focused on orchestration.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from solarbatteryield.models import SimulationInput
from solarbatteryield.simulation.h0_profile import get_h0_load, get_day_type, get_season, DayType, Season


def calculate_hourly_load(
    hour: int,
    current_date: date,
    params: SimulationInput,
    day: int,
    use_flex_today: bool,
    hour_index: int = 0,
) -> float:
    """
    Calculate the load for a specific hour.

    For simple mode: Uses BDEW H0 standard load profile with day type differentiation
    For advanced mode: Uses user-provided profiles with optional seasonal scaling
    For expert mode: Uses uploaded yearly hourly profile directly
    """
    month = current_date.month
    consumption = params.consumption

    if params.use_yearly_profile():
        # Expert mode: Use the yearly profile directly
        # Profile values are in Watts, convert to kWh
        load = consumption.yearly_profile[hour_index] / 1000
    elif params.use_h0_profile():
        # Simple mode: Use H0 profile
        # get_h0_load returns kWh directly
        load = get_h0_load(hour, current_date, consumption.annual_kwh)
    else:
        # Advanced mode: Use user-provided profiles
        day_type = get_day_type(current_date)

        # Select appropriate profile based on day type
        if params.has_day_type_profiles():
            if day_type == DayType.SATURDAY:
                profile = consumption.profile_saturday
            elif day_type == DayType.SUNDAY:
                profile = consumption.profile_sunday
            else:
                profile = consumption.active_base
        else:
            profile = consumption.active_base

        # Get base load from profile (convert W to kWh)
        load = profile[hour] / 1000

        # Apply seasonal scaling (only in advanced mode)
        if consumption.seasonal_enabled:
            season = get_season(month, current_date.day)
            season_factors = {
                Season.WINTER: consumption.season_winter_pct / 100,
                Season.SUMMER: consumption.season_summer_pct / 100,
                Season.TRANSITION: 1.0,
            }
            load *= season_factors[season]

    # Add flexible load if applicable
    if use_flex_today:
        load += consumption.flex_delta[hour] / 1000

    # Add periodic load if applicable
    if consumption.periodic_enabled and day % consumption.periodic_days == 0:
        load += consumption.periodic_delta[hour] / 1000

    return load


def update_flex_pool(
    hour: int,
    day: int,
    pv_raw: np.ndarray,
    hour_index: int,
    flex_pool: float,
    params: SimulationInput,
    use_flex_today: bool = False,
) -> tuple[bool, float]:
    """
    Update flexible load pool at the start of each day.

    Pure function: returns (use_flex_today, new_flex_pool) instead of mutating state.
    At non-zero hours, returns the previous use_flex_today unchanged.
    """
    if hour != 0:
        return use_flex_today, flex_pool  # Not start of day — keep previous values

    consumption = params.consumption
    day_yield = float(sum(pv_raw[hour_index: hour_index + 24]))

    # Refresh pool every day (e.g., new laundry accumulates daily)
    flex_pool = min(float(consumption.flex_pool), flex_pool + consumption.flex_refresh)

    if (consumption.flex_enabled
            and day_yield > consumption.flex_min_yield
            and flex_pool >= 1.0):
        return True, flex_pool - 1.0
    else:
        return False, flex_pool


