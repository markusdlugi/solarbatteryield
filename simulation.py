"""
Core simulation engine for the PV analysis application.
Handles energy flow simulation with battery storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from models import SimulationParams, MonthlyData, HourlyResult, SimulationResult
from h0_profile import (
    get_h0_load, get_day_type, get_season as get_h0_season, 
    DayType, Season, H0_PROFILES
)


# Season definitions - centralized for consistency
WINTER_MONTHS = frozenset({11, 12, 1, 2, 3})
SUMMER_MONTHS = frozenset({5, 6, 7, 8, 9})
TRANSITION_MONTHS = frozenset({4, 10})



@dataclass
class SimulationState:
    """Mutable state tracked during simulation."""
    soc: float = 0.0
    grid_import: float = 0.0
    feed_in: float = 0.0
    curtailed: float = 0.0
    total_consumption: float = 0.0
    flex_pool: float = 0.0
    use_flex_today: bool = False
    
    # Derived values set per-hour
    batt_eff: float = 1.0
    inv_eff: float = 1.0
    inv_cap: float = float('inf')
    min_soc: float = 0.0
    max_soc: float = 0.0
    
    def accumulate_result(self, result: HourlyResult) -> None:
        """Add hourly result values to running totals."""
        self.grid_import += result.grid_import
        self.feed_in += result.feed_in
        self.curtailed += result.curtailed


def get_season(month: int) -> str:
    """Return season name for a given month (1-12)."""
    if month in WINTER_MONTHS:
        return "winter"
    elif month in SUMMER_MONTHS:
        return "summer"
    return "transition"


def is_winter_month(month: int) -> bool:
    """Check if month is considered winter for SoC limits."""
    return month in {10, 11, 12, 1, 2, 3}


def _calculate_hourly_load(
    hour: int,
    current_date: date,
    params: SimulationParams,
    day: int,
    use_flex_today: bool,
) -> float:
    """
    Calculate the load for a specific hour.
    
    For simple mode: Uses BDEW H0 standard load profile with day type differentiation
    For advanced mode: Uses user-provided profiles with optional seasonal scaling
    """
    month = current_date.month
    
    if params.use_h0_profile():
        # Simple mode: Use H0 profile
        # get_h0_load returns kWh directly
        load = get_h0_load(hour, current_date, params.annual_kwh)
    else:
        # Advanced mode: Use user-provided profiles
        day_type = get_day_type(current_date)
        
        # Select appropriate profile based on day type
        if params.has_day_type_profiles():
            if day_type == DayType.SATURDAY:
                profile = params.profile_saturday
            elif day_type == DayType.SUNDAY:
                profile = params.profile_sunday
            else:
                profile = params.profile_base
        else:
            profile = params.profile_base
        
        # Get base load from profile (convert W to kWh)
        load = profile[hour] / 1000
        
        # Apply seasonal scaling (only in advanced mode)
        if params.seasonal_enabled:
            season = get_season(month)
            season_factors = {
                "winter": params.season_winter_pct / 100,
                "summer": params.season_summer_pct / 100,
                "transition": 1.0,
            }
            load *= season_factors[season]
    
    # Add flexible load if applicable
    if use_flex_today:
        load += params.flex_delta[hour] / 1000
    
    # Add periodic load if applicable
    if params.periodic_load_enabled and day % params.periodic_interval_days == 0:
        load += params.periodic_delta[hour] / 1000
    
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
    inv_eff = state.inv_eff
    inv_cap = state.inv_cap
    batt_eff = state.batt_eff
    min_soc = state.min_soc
    max_soc = state.max_soc
    soc = state.soc
    
    # Step 1: Cover load directly from PV (through inverter)
    dc_needed_for_load = min(gen_dc, load / inv_eff, inv_cap / inv_eff)
    pv_to_load_ac = dc_needed_for_load * inv_eff
    load_deficit = load - pv_to_load_ac
    
    # Step 2: Charge battery from remaining DC (no inverter limit)
    dc_remaining = gen_dc - dc_needed_for_load
    charge = min(dc_remaining, (max_soc - soc) / batt_eff) if cap_gross > 0 else 0
    soc += charge * batt_eff
    dc_after_charge = dc_remaining - charge
    
    # Step 3: Export surplus through inverter (limited by remaining capacity)
    remaining_inv_dc = max(0, inv_cap / inv_eff - dc_needed_for_load)
    dc_to_export = min(dc_after_charge, remaining_inv_dc)
    export_ac = dc_to_export * inv_eff
    curtailed = dc_after_charge - dc_to_export
    
    # Step 4: Cover deficit from battery or grid
    grid_import = 0.0
    battery_discharge = 0.0
    
    if load_deficit > 0:
        inv_headroom_dc = max(0, inv_cap / inv_eff - dc_needed_for_load - dc_to_export)
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
    
    AC-coupled: inverter converts all PV to AC first, then battery charges from AC.
    """
    inv_eff = state.inv_eff
    inv_cap = state.inv_cap
    batt_eff = state.batt_eff
    min_soc = state.min_soc
    max_soc = state.max_soc
    soc = state.soc
    
    # Step 1: Convert DC to AC (limited by inverter)
    dc_to_inverter = min(gen_dc, inv_cap / inv_eff)
    gen_ac = dc_to_inverter * inv_eff
    curtailed = gen_dc - dc_to_inverter
    
    net = gen_ac - load
    
    grid_import = 0.0
    feed_in = 0.0
    direct_pv = 0.0
    battery_discharge = 0.0
    
    if net > 0:
        # Surplus: charge battery, then feed in
        charge = min(net, (max_soc - soc) / batt_eff) if cap_gross > 0 else 0
        soc += charge * batt_eff
        feed_in = net - charge
        direct_pv = load
    else:
        # Deficit: discharge battery or import from grid
        deficit = abs(net)
        discharge = min(deficit / batt_eff, max(0, soc - min_soc)) if cap_gross > 0 else 0
        soc -= discharge
        battery_discharge = discharge * batt_eff
        grid_import = deficit - battery_discharge
        direct_pv = gen_ac
    
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
    params: SimulationParams,
) -> None:
    """Update flexible load pool at the start of each day."""
    if hour != 0:
        return
    
    day_yield = sum(pv_raw[hour_index: hour_index + 24])
    
    if (params.flex_load_enabled and 
        day_yield > params.flex_min_yield and 
        state.flex_pool >= 1.0):
        state.use_flex_today = True
        state.flex_pool -= 1.0
    else:
        state.use_flex_today = False
        state.flex_pool = min(float(params.flex_pool_size), state.flex_pool + params.flex_refresh_rate)


def simulate(
    pv_raw: np.ndarray, 
    cap_gross: float, 
    params: SimulationParams
) -> SimulationResult:
    """
    Run hourly simulation of PV system with battery storage.
    
    Args:
        pv_raw: Array of hourly PV generation values in kWh
        cap_gross: Battery capacity in kWh
        params: Simulation parameters dataclass
        
    Returns:
        SimulationResult containing energy totals and monthly breakdown
    """
    hours = len(pv_raw)
    
    # Initialize state
    state = SimulationState(
        flex_pool=float(params.flex_pool_size),
        batt_eff=1 - params.batt_loss_pct / 100,
        inv_eff=params.inverter_eff_pct / 100,
        inv_cap=params.inverter_limit_kw if params.inverter_limit_kw is not None else float('inf'),
    )
    
    # Select processing function based on coupling type
    process_hour = _process_hour_dc_coupled if params.dc_coupled else _process_hour_ac_coupled
    
    # Monthly tracking
    monthly: dict[int, MonthlyData] = {m: MonthlyData() for m in range(1, 13)}
    
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
        if is_winter_month(month):
            state.min_soc = cap_gross * params.min_soc_winter_pct / 100
            state.max_soc = cap_gross * params.max_soc_winter_pct / 100
        else:
            state.min_soc = cap_gross * params.min_soc_summer_pct / 100
            state.max_soc = cap_gross * params.max_soc_summer_pct / 100
        
        # Calculate load for this hour (handles both H0 and custom profiles)
        load = _calculate_hourly_load(
            hour, current_date, params, day, state.use_flex_today
        )
        
        gen_dc = pv_raw[i]
        state.total_consumption += load
        
        # Process the hour
        result = process_hour(gen_dc, load, state, cap_gross)
        
        # Accumulate totals
        state.accumulate_result(result)
        monthly[month].add_hourly_result(result)
    
    return SimulationResult(
        grid_import=state.grid_import,
        total_consumption=state.total_consumption,
        feed_in=state.feed_in,
        curtailed=state.curtailed,
        monthly=monthly,
    )
