"""
Core simulation engine for the PV analysis application.
Orchestrates the hourly simulation loop using Battery and load modules.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from solarbatteryield.models import SimulationInput, MonthlyData, SimulationResult
from solarbatteryield.simulation.h0_profile import get_season, Season
from solarbatteryield.simulation.load import calculate_hourly_load, update_flex_pool
from solarbatteryield.simulation.battery import create_battery
from solarbatteryield.simulation.weekly_recorder import WeeklySoCRecorder


def simulate(
    pv_raw: np.ndarray,
    cap_gross: float,
    params: SimulationInput,
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

    # Create battery (NoBattery when cap_gross <= 0)
    battery = create_battery(
        cap_gross=cap_gross,
        batt_eff=1 - storage.batt_loss / 100,
        inv_cap=params.inverter_limit_kw if params.inverter_limit_kw is not None else float('inf'),
        inv_eff_curve=params.inverter_efficiency_curve,
        dc_coupled=storage.dc_coupled,
        batt_inv_eff_curve=params.batt_inverter_efficiency_curve,
    )

    # Running totals
    total_consumption = 0.0
    grid_import = 0.0
    feed_in = 0.0
    curtailed = 0.0

    # Flex pool tracking
    flex_pool = float(params.consumption.flex_pool)
    use_flex_today = False

    # Monthly tracking
    monthly: dict[int, MonthlyData] = {m: MonthlyData() for m in range(1, 13)}

    # Weekly SoC recording (no-op when cap_gross <= 0)
    soc_recorder = WeeklySoCRecorder(params.data_year, cap_gross)

    # Start date for the simulation year
    start_date = date(params.data_year, 1, 1)

    for i in range(hours):
        hour = i % 24
        day = i // 24

        # Calculate current date
        current_date = start_date + timedelta(days=day)
        month = current_date.month

        # Update flex pool at start of day
        use_flex_today, flex_pool = update_flex_pool(
            hour, day, pv_raw, i, flex_pool, params, use_flex_today
        )

        # Season-dependent SoC limits
        if get_season(month, current_date.day) == Season.WINTER:
            battery.set_soc_limits(
                cap_gross * storage.min_soc_winter / 100,
                cap_gross * storage.max_soc_winter / 100,
            )
        else:
            battery.set_soc_limits(
                cap_gross * storage.min_soc_summer / 100,
                cap_gross * storage.max_soc_summer / 100,
            )

        # Calculate load for this hour
        load = calculate_hourly_load(
            hour, current_date, params, day, use_flex_today, hour_index=i
        )

        gen_dc = pv_raw[i]
        total_consumption += load

        # Energy flow
        result = battery.process_hour(gen_dc, load, hour)

        # Accumulate totals
        grid_import += result.grid_import
        feed_in += result.feed_in
        curtailed += result.curtailed
        monthly[month].add_hourly_result(result)

        # Record weekly SoC data for representative weeks
        soc_recorder.record(i, battery, gen_dc, load)

    # Calculate full cycles: total discharge energy / battery capacity
    full_cycles = battery.total_discharge / cap_gross if cap_gross > 0 else 0.0

    return SimulationResult(
        grid_import=grid_import,
        total_consumption=total_consumption,
        feed_in=feed_in,
        curtailed=curtailed,
        monthly=monthly,
        full_cycles=full_cycles,
        weekly_summer=soc_recorder.weekly_summer,
        weekly_winter=soc_recorder.weekly_winter,
        weekly_transition=soc_recorder.weekly_transition,
    )
