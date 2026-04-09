"""
Core simulation engine for the PV analysis application.
Handles energy flow simulation with battery storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import NamedTuple

import numpy as np

from solarbatteryield.models import SimulationInput, MonthlyData, HourlyResult, SimulationResult, WeeklyHourlyData
from solarbatteryield.h0_profile import get_h0_load, get_day_type, get_season, DayType, Season
from solarbatteryield.inverter_efficiency import (
    get_inverter_efficiency,
    DEFAULT_INVERTER_EFFICIENCY_CURVE,
)
from solarbatteryield.load_regression import get_direct_pv_fraction



@dataclass
class SimulationState:
    """Mutable state tracked during simulation."""
    soc: float = 0.0
    grid_import: float = 0.0
    feed_in: float = 0.0
    curtailed: float = 0.0
    total_consumption: float = 0.0
    total_battery_discharge: float = 0.0
    flex_pool: float = 0.0
    use_flex_today: bool = False
    
    # Derived values set per-hour
    batt_eff: float = 1.0
    inv_cap: float = float('inf')
    min_soc: float = 0.0
    max_soc: float = 0.0
    
    # Inverter efficiency curve
    inverter_efficiency_curve: tuple[tuple[int, float], ...] = field(
        default_factory=lambda: DEFAULT_INVERTER_EFFICIENCY_CURVE
    )
    
    # Battery inverter efficiency curve (AC-coupled only)
    batt_inverter_efficiency_curve: tuple[tuple[int, float], ...] = field(
        default_factory=lambda: DEFAULT_INVERTER_EFFICIENCY_CURVE
    )
    
    def get_inverter_efficiency(self, power_kw: float) -> float:
        """
        Get PV inverter efficiency for current power level.
        """
        return get_inverter_efficiency(power_kw, self.inv_cap, self.inverter_efficiency_curve)
    
    def get_batt_inverter_efficiency(self, power_kw: float, cap_kw: float) -> float:
        """
        Get battery inverter efficiency for current power level.
        
        Args:
            power_kw: Current power through the battery inverter in kW
            cap_kw: Battery capacity in kWh (used as rated power reference, 1C assumption)
        """
        return get_inverter_efficiency(power_kw, cap_kw, self.batt_inverter_efficiency_curve)

    def accumulate_result(self, result: HourlyResult) -> None:
        """Add hourly result values to running totals."""
        self.grid_import += result.grid_import
        self.feed_in += result.feed_in
        self.curtailed += result.curtailed
        self.total_battery_discharge += result.battery_discharge




def _calculate_hourly_load(
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


def _process_hour_dc_coupled(
    gen_dc: float,
    load: float,
    state: SimulationState,
    cap_gross: float,
) -> HourlyResult:
    """
    Process one hour with DC-coupled battery.
    
    DC-coupled: battery on DC bus, inverter limit on AC only.
    Priority: Load -> Battery charge -> Feed-in (limited by inverter)
    """
    inv_cap = state.inv_cap
    batt_eff = state.batt_eff
    min_soc = state.min_soc
    max_soc = state.max_soc
    soc = state.soc
    
    # Get efficiency based on expected power through inverter
    # For DC-coupled, we estimate based on the DC generation that will go through inverter
    inv_eff = state.get_inverter_efficiency(min(gen_dc, inv_cap))
    
    # Step 1: Determine maximum AC available from PV for load coverage
    max_dc_for_load = min(gen_dc, load / inv_eff, inv_cap / inv_eff)
    max_pv_to_load_ac = max_dc_for_load * inv_eff
    
    # Apply sub-hourly load regression to get realistic direct-PV fraction.
    # Within the hour the load varies, so not all of min(load, pv_ac) is
    # actually self-consumed — some moments the load drops below PV and
    # the surplus cannot be absorbed as "direct PV".
    fraction = get_direct_pv_fraction(load * 1000, max_pv_to_load_ac * 1000)
    pv_to_load_ac = fraction * min(load, max_pv_to_load_ac)
    actual_dc_for_load = pv_to_load_ac / inv_eff if inv_eff > 0 else 0.0
    load_deficit = load - pv_to_load_ac
    
    # Step 2: Charge battery from remaining DC (no inverter limit)
    dc_remaining = gen_dc - actual_dc_for_load
    charge = min(dc_remaining, (max_soc - soc) / batt_eff) if cap_gross > 0 else 0
    soc += charge * batt_eff
    dc_after_charge = dc_remaining - charge
    
    # Step 3: Export surplus through inverter (limited by remaining capacity)
    remaining_inv_dc = max(0, inv_cap / inv_eff - actual_dc_for_load)
    dc_to_export = min(dc_after_charge, remaining_inv_dc)
    export_ac = dc_to_export * inv_eff
    curtailed = dc_after_charge - dc_to_export
    
    # Step 4: Cover deficit from battery or grid
    grid_import = 0.0
    battery_discharge = 0.0
    
    if load_deficit > 0:
        inv_headroom_dc = max(0, inv_cap / inv_eff - actual_dc_for_load - dc_to_export)
        combined_eff = batt_eff * inv_eff
        max_discharge = (
            min(load_deficit / combined_eff, max(0, soc - min_soc), inv_headroom_dc / inv_eff / batt_eff)
            if cap_gross > 0 else 0
        )
        soc -= max_discharge
        from_batt_ac = max_discharge * combined_eff
        grid_import = load_deficit - from_batt_ac
        battery_discharge = from_batt_ac
    
    # Update state
    state.soc = soc
    
    return HourlyResult(
        grid_import=grid_import,
        feed_in=export_ac,
        curtailed=curtailed,
        direct_pv=pv_to_load_ac,
        battery_discharge=battery_discharge,
        pv_generation=gen_dc,
        consumption=load,
    )


def _process_hour_ac_coupled(
    gen_dc: float,
    load: float,
    state: SimulationState,
    cap_gross: float,
) -> HourlyResult:
    """
    Process one hour with AC-coupled battery.
    
    AC-coupled: inverter converts all PV to AC first, then battery charges from AC
    through its own bidirectional inverter (batt_inv_eff).
    """
    inv_cap = state.inv_cap
    batt_eff = state.batt_eff
    min_soc = state.min_soc
    max_soc = state.max_soc
    soc = state.soc
    
    # Get PV inverter efficiency
    inv_eff = state.get_inverter_efficiency(min(gen_dc, inv_cap))
    
    # Step 1: Convert DC to AC (limited by PV inverter)
    dc_to_inverter = min(gen_dc, inv_cap / inv_eff)
    gen_ac = dc_to_inverter * inv_eff
    curtailed = gen_dc - dc_to_inverter
    
    # Apply sub-hourly load regression to determine realistic direct-PV usage.
    # Both surplus and deficit can coexist: during low-load moments PV exceeds
    # demand (surplus), while during high-load moments demand exceeds PV (deficit).
    fraction = get_direct_pv_fraction(load * 1000, gen_ac * 1000)
    direct_pv = fraction * min(load, gen_ac)
    
    surplus = gen_ac - direct_pv
    deficit = load - direct_pv
    
    # Handle surplus: charge battery (through battery inverter), then feed in
    feed_in = 0.0
    if surplus > 0:
        # Battery inverter efficiency for charging (AC → DC)
        batt_inv_eff = state.get_batt_inverter_efficiency(surplus, cap_gross) if cap_gross > 0 else 1.0
        combined_charge_eff = batt_inv_eff * batt_eff
        charge = min(surplus, (max_soc - soc) / combined_charge_eff) if cap_gross > 0 else 0
        soc += charge * combined_charge_eff
        feed_in = surplus - charge
    
    # Handle deficit: discharge battery (through battery inverter) or import from grid
    grid_import = 0.0
    battery_discharge = 0.0
    if deficit > 0:
        # Battery inverter efficiency for discharging (DC → AC)
        batt_inv_eff = state.get_batt_inverter_efficiency(deficit, cap_gross) if cap_gross > 0 else 1.0
        combined_discharge_eff = batt_eff * batt_inv_eff
        discharge = min(deficit / combined_discharge_eff, max(0, soc - min_soc)) if cap_gross > 0 else 0
        soc -= discharge
        battery_discharge = discharge * combined_discharge_eff
        grid_import = deficit - battery_discharge
    
    # Update state
    state.soc = soc
    
    return HourlyResult(
        grid_import=grid_import,
        feed_in=feed_in,
        curtailed=curtailed,
        direct_pv=direct_pv,
        battery_discharge=battery_discharge,
        pv_generation=gen_dc,
        consumption=load,
    )


def _update_flex_pool(
    hour: int,
    day: int,
    pv_raw: np.ndarray,
    hour_index: int,
    state: SimulationState,
    params: SimulationInput,
) -> None:
    """Update flexible load pool at the start of each day."""
    if hour != 0:
        return
    
    day_yield = sum(pv_raw[hour_index: hour_index + 24])
    consumption = params.consumption
    
    # Refresh pool every day (e.g., new laundry accumulates daily)
    state.flex_pool = min(float(consumption.flex_pool), state.flex_pool + consumption.flex_refresh)
    
    if (consumption.flex_enabled and 
        day_yield > consumption.flex_min_yield and 
        state.flex_pool >= 1.0):
        state.use_flex_today = True
        state.flex_pool -= 1.0
    else:
        state.use_flex_today = False


class _WeeklyTracker(NamedTuple):
    """Tracks hourly SoC data for a specific week in the year."""
    data: WeeklyHourlyData
    hour_start: int
    hour_end: int


def _build_weekly_trackers(data_year: int, cap_gross: float) -> list[_WeeklyTracker]:
    """
    Create weekly SoC trackers for representative weeks per season.
    
    Returns empty list if no battery (cap_gross == 0).
    Weeks selected:
      - Summer:     July 1–7   (first week of July)
      - Transition: April 8–14 (second week of April)
      - Winter:     Jan 8–14   (second week of January)
    """
    if cap_gross <= 0:
        return []
    
    is_leap = data_year % 4 == 0 and (data_year % 100 != 0 or data_year % 400 == 0)
    
    # 0-indexed day-of-year for the start of each representative week
    week_start_days = {
        "summer": 182 if not is_leap else 183,      # July 1st
        "transition": 98 if not is_leap else 99,     # April 8th
        "winter": 7,                                  # January 8th
    }
    
    return [
        _WeeklyTracker(
            data=WeeklyHourlyData(),
            hour_start=start_day * 24,
            hour_end=start_day * 24 + 168,
        )
        for start_day in week_start_days.values()
    ]


def simulate(
    pv_raw: np.ndarray, 
    cap_gross: float, 
    params: SimulationInput
) -> SimulationResult:
    """
    Run hourly simulation of PV system with battery storage.
    
    Args:
        pv_raw: Array of hourly PV generation values in kWh
        cap_gross: Battery capacity in kWh
        params: Simulation input composing consumption and storage config
        
    Returns:
        SimulationResult containing energy totals and monthly breakdown
    """
    hours = len(pv_raw)
    storage = params.storage
    
    # Initialize state
    state = SimulationState(
        flex_pool=float(params.consumption.flex_pool),
        batt_eff=1 - storage.batt_loss / 100,
        inv_cap=params.inverter_limit_kw if params.inverter_limit_kw is not None else float('inf'),
        inverter_efficiency_curve=params.inverter_efficiency_curve,
        batt_inverter_efficiency_curve=params.batt_inverter_efficiency_curve,
    )
    
    # Select processing function based on coupling type
    process_hour = _process_hour_dc_coupled if storage.dc_coupled else _process_hour_ac_coupled
    
    # Monthly tracking
    monthly: dict[int, MonthlyData] = {m: MonthlyData() for m in range(1, 13)}
    
    # Weekly SoC tracking for representative weeks (summer, transition, winter)
    weekly_trackers = _build_weekly_trackers(params.data_year, cap_gross)
    
    # Start date for the simulation year
    start_date = date(params.data_year, 1, 1)
    
    for i in range(hours):
        hour = i % 24
        day = i // 24
        
        # Calculate current date
        current_date = start_date + timedelta(days=day)
        month = current_date.month
        
        # Update flex pool at start of day
        _update_flex_pool(hour, day, pv_raw, i, state, params)
        
        # Set SoC limits based on season
        if get_season(month, current_date.day) == Season.WINTER:
            state.min_soc = cap_gross * storage.min_soc_winter / 100
            state.max_soc = cap_gross * storage.max_soc_winter / 100
        else:
            state.min_soc = cap_gross * storage.min_soc_summer / 100
            state.max_soc = cap_gross * storage.max_soc_summer / 100
        
        # Calculate load for this hour (handles H0, custom, and yearly profiles)
        load = _calculate_hourly_load(
            hour, current_date, params, day, state.use_flex_today, hour_index=i
        )
        
        gen_dc = pv_raw[i]
        state.total_consumption += load
        
        # Process the hour
        result = process_hour(gen_dc, load, state, cap_gross)
        
        # Accumulate totals
        state.accumulate_result(result)
        monthly[month].add_hourly_result(result)
        
        # Capture weekly SoC data for representative weeks
        if cap_gross > 0:
            soc_pct = (state.soc / cap_gross) * 100
            for tracker in weekly_trackers:
                if tracker.hour_start <= i < tracker.hour_end:
                    tracker.data.add_hour(
                        hour=i - tracker.hour_start,
                        soc=state.soc,
                        soc_pct=soc_pct,
                        pv_generation=gen_dc,
                        consumption=load
                    )
    
    # Calculate full cycles: total discharge energy / battery capacity
    full_cycles = state.total_battery_discharge / cap_gross if cap_gross > 0 else 0.0
    
    # Unpack weekly trackers: summer, transition, winter (order from _build_weekly_trackers)
    weekly_summer = weekly_trackers[0].data if weekly_trackers else None
    weekly_transition = weekly_trackers[1].data if weekly_trackers else None
    weekly_winter = weekly_trackers[2].data if weekly_trackers else None
    
    return SimulationResult(
        grid_import=state.grid_import,
        total_consumption=state.total_consumption,
        feed_in=state.feed_in,
        curtailed=state.curtailed,
        monthly=monthly,
        full_cycles=full_cycles,
        weekly_summer=weekly_summer,
        weekly_winter=weekly_winter,
        weekly_transition=weekly_transition,
    )
