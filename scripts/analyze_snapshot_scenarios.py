#!/usr/bin/env python3
"""
Analyze snapshot test scenarios to understand PV generation vs load patterns.

This script helps debug why different battery sizes might show similar results.
Run with: uv run python scripts/analyze_snapshot_scenarios.py
"""
import numpy as np
from tests.test_snapshots import (
    _create_synthetic_pv_data, 
    _create_realistic_load_profile,
    _create_simulation_params,
)
from solarbatteryield.simulation import simulate


def analyze_pv_and_load():
    """Analyze PV generation and load patterns."""
    pv = _create_synthetic_pv_data()
    load_profile = _create_realistic_load_profile()
    
    print("=" * 60)
    print("PV GENERATION ANALYSIS")
    print("=" * 60)
    
    # Total annual PV generation
    total_pv = sum(pv)
    print(f"\nTotal annual PV generation: {total_pv:.1f} kWh")
    
    # Peak daily PV in summer (around day 172 = June 21)
    summer_day_start = 172 * 24
    summer_day = pv[summer_day_start:summer_day_start+24]
    print(f"\nPeak summer day (day 172) PV: {sum(summer_day):.2f} kWh")
    print(f"Peak hour PV power: {max(summer_day):.3f} kW")
    
    # Winter day (Jan 1)
    winter_day = pv[0:24]
    print(f"Winter day (Jan 1) PV: {sum(winter_day):.2f} kWh")
    
    print("\n" + "=" * 60)
    print("LOAD ANALYSIS")
    print("=" * 60)
    
    # Total load
    daily_load = sum(load_profile) / 1000  # kWh
    annual_load = daily_load * 365
    print(f"\nDaily load: {daily_load:.2f} kWh")
    print(f"Annual load: {annual_load:.1f} kWh")
    
    print("\n" + "=" * 60)
    print("SURPLUS ANALYSIS (what battery can store)")
    print("=" * 60)
    
    # Calculate hourly surplus for summer day
    summer_surplus_hourly = []
    for hour in range(24):
        pv_hour = summer_day[hour]
        load_hour = load_profile[hour] / 1000  # Convert W to kW
        surplus = max(0, pv_hour - load_hour)
        summer_surplus_hourly.append(surplus)
    
    total_summer_surplus = sum(summer_surplus_hourly)
    print(f"\nSummer day surplus (what can be stored): {total_summer_surplus:.2f} kWh")
    print(f"  -> A 3 kWh battery can store: {min(3.0, total_summer_surplus):.2f} kWh")
    print(f"  -> A 10 kWh battery can store: {min(10.0, total_summer_surplus):.2f} kWh")
    
    if total_summer_surplus < 3.0:
        print("\n⚠️  WARNING: Daily surplus is less than 3 kWh!")
        print("   Both battery sizes will behave identically because")
        print("   there's not enough surplus to fill even the small battery.")


def run_battery_comparison():
    """Run simulations with different battery sizes and compare."""
    print("\n" + "=" * 60)
    print("BATTERY SIZE COMPARISON")
    print("=" * 60)
    
    params = _create_simulation_params(
        profile_base=_create_realistic_load_profile(),
    )
    pv_data = _create_synthetic_pv_data()
    
    results = {}
    for cap in [0.0, 3.0, 5.0, 10.0]:
        result = simulate(pv_data, cap_gross=cap, params=params)
        results[cap] = result
        print(f"\nBattery {cap:5.1f} kWh:")
        print(f"  Grid import: {result.grid_import:8.1f} kWh")
        print(f"  Feed-in:     {result.feed_in:8.1f} kWh")
        print(f"  Full cycles: {result.full_cycles:8.1f}")
    
    # Calculate improvements
    baseline = results[0.0].grid_import
    print("\n" + "-" * 40)
    print("Grid import reduction vs no battery:")
    for cap in [3.0, 5.0, 10.0]:
        reduction = baseline - results[cap].grid_import
        print(f"  {cap:5.1f} kWh battery: -{reduction:.1f} kWh ({100*reduction/baseline:.1f}%)")


def test_with_higher_pv():
    """Test with increased PV to see battery size difference."""
    print("\n" + "=" * 60)
    print("TEST WITH HIGHER PV (2x power)")
    print("=" * 60)
    
    # Create PV data with 2x power
    pv_data = _create_synthetic_pv_data() * 2.0
    
    params = _create_simulation_params(
        profile_base=_create_realistic_load_profile(),
        inverter_limit_kw=None,  # Remove inverter limit for this test
    )
    
    results = {}
    for cap in [0.0, 3.0, 5.0, 10.0]:
        result = simulate(pv_data, cap_gross=cap, params=params)
        results[cap] = result
        print(f"\nBattery {cap:5.1f} kWh:")
        print(f"  Grid import: {result.grid_import:8.1f} kWh")
        print(f"  Feed-in:     {result.feed_in:8.1f} kWh")
        print(f"  Full cycles: {result.full_cycles:8.1f}")
    
    # Calculate improvements
    baseline = results[0.0].grid_import
    print("\n" + "-" * 40)
    print("Grid import reduction vs no battery:")
    for cap in [3.0, 5.0, 10.0]:
        reduction = baseline - results[cap].grid_import
        print(f"  {cap:5.1f} kWh battery: -{reduction:.1f} kWh ({100*reduction/baseline:.1f}%)")


if __name__ == "__main__":
    analyze_pv_and_load()
    run_battery_comparison()
    test_with_higher_pv()

