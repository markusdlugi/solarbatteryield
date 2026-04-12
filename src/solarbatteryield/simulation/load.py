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


def compute_min_load_w(params: SimulationInput) -> float:
    """
    Derive the base-load floor (watts) from the user's load configuration.

    The floor represents the always-on household draw (fridge, router, standby).
    It is used by the two-layer regression model in ``get_direct_pv_fraction``.

    All modes produce *hourly average* values, which slightly overstate the
    true instantaneous base load — even the quietest hour contains brief spikes
    from fridge cycling, etc.  A scaling factor of 0.9 is applied to convert
    from "minimum hourly average" to "estimated always-on floor".

    Empirical basis (Schlemminger 2019 dataset, 28 households):

    * P1 (minute-level 1st-percentile base load) / min(all hourly avg):
      median **0.96**.  However, the absolute minimum hour falls during
      *daytime* for 74% of households (absence / vacation anomalies),
      making this ratio misleadingly high.
    * P1 / min(night hourly avg, 23:00–04:59): median **0.88**.
      Night hours better represent the always-on load without absence
      effects.
    * We use **0.9** as a pragmatic compromise between the two medians
      (0.88 night, 0.96 all-hours).  It is easy to reason about
      ("~90% of the minimum hourly average is true base load") and
      conservative enough to avoid overestimating the floor.

    Mode logic (before scaling):

    * **Expert** (yearly profile provided): ``min(yearly_profile)``
    * **Simple** (H0 profile): ``min(H0 hourly values over sample dates)``
    * **Advanced** (active_base ± seasonal): ``min(active_base) × season_summer_pct / 100``

    Returns:
        Base-load floor in watts (≥ 0).
    """
    # Hourly average → instantaneous base load conversion factor.
    # Schlemminger 2019 data, 28 households:
    #   P1 / min(all hourly avg)  : median 0.96  (biased by daytime absence)
    #   P1 / min(night hourly avg): median 0.88  (stable, no absence effect)
    # 0.9 is a round compromise.
    _HOURLY_TO_BASE_RATIO = 0.9

    consumption = params.consumption

    if params.use_yearly_profile():
        min_hourly_w = float(min(consumption.yearly_profile))
        return max(0.0, min_hourly_w * _HOURLY_TO_BASE_RATIO)

    if params.use_h0_profile():
        from solarbatteryield.simulation.h0_profile import get_h0_load

        min_load_kwh = float("inf")
        sample_dates = [
            date(params.data_year, 1, 15),  # winter weekday
            date(params.data_year, 1, 18),  # winter Saturday
            date(params.data_year, 1, 19),  # winter Sunday
            date(params.data_year, 4, 15),  # transition
            date(params.data_year, 7, 15),  # summer weekday
            date(params.data_year, 7, 18),  # summer Saturday
            date(params.data_year, 7, 19),  # summer Sunday
        ]
        for d in sample_dates:
            for hour in range(24):
                load_kwh = get_h0_load(hour, d, consumption.annual_kwh)
                min_load_kwh = min(min_load_kwh, load_kwh)

        return max(0.0, min_load_kwh * 1000 * _HOURLY_TO_BASE_RATIO)

    # Advanced mode: active_base is in watts (hourly averages)
    base_min = min(consumption.active_base)

    if consumption.seasonal_enabled:
        base_min *= consumption.season_summer_pct / 100

    return max(0.0, float(base_min) * _HOURLY_TO_BASE_RATIO)
