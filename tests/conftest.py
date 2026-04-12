"""
Shared pytest fixtures for the SolarBatterYield test suite.

This module provides common fixtures and helper functions used across multiple
test modules to reduce duplication and ensure consistency.
"""
import numpy as np
import pytest

from solarbatteryield.models import (
    SimulationInput, ConsumptionConfig, StorageConfig, DischargeStrategyConfig,
)
from solarbatteryield.simulation.inverter_efficiency import (
    INVERTER_EFFICIENCY_CURVES,
)


# ─── Simulation Parameters Fixtures ──────────────────────────────────────────


@pytest.fixture
def base_simulation_params() -> SimulationInput:
    """
    Create base SimulationInput with sensible defaults.
    
    This is the foundation for most simulation tests. Use this fixture and
    override specific fields as needed.
    """
    return create_simulation_params()


@pytest.fixture
def expert_mode_params() -> SimulationInput:
    """
    Create SimulationInput configured for expert mode with a constant yearly profile.
    
    Expert mode uses a complete yearly hourly load profile instead of
    standard profiles or custom daily patterns.
    """
    return create_simulation_params(
        profile_mode="Experte",
        annual_kwh=None,
        yearly_profile=[200.0] * 8760,  # Constant 200W load
    )


# ─── PV Data Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def zero_pv_data() -> np.ndarray:
    """Create PV data array with no generation (8760 hours of zeros)."""
    return np.zeros(8760)


@pytest.fixture
def constant_pv_data() -> np.ndarray:
    """Create constant 1kW PV generation for all hours."""
    return create_constant_pv(power_kw=1.0)


@pytest.fixture
def daytime_pv_data() -> np.ndarray:
    """Create PV data with 1kW generation during daytime hours (6-18) only."""
    return create_daytime_pv(peak_kw=1.0)


@pytest.fixture
def synthetic_pv_data() -> np.ndarray:
    """
    Create realistic synthetic PV data with seasonal variation.
    
    Simulates a ~2 kWp system with:
    - Bell curve daily pattern (peak at noon)
    - Seasonal variation (more in summer, less in winter)
    """
    return create_synthetic_pv_data()


# ─── Load Profile Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def constant_load_profile() -> list[float]:
    """Create a constant 200W load profile for 24 hours."""
    return [200.0] * 24


@pytest.fixture
def realistic_load_profile() -> list[float]:
    """
    Create a realistic daily load profile in Watts.
    
    Pattern:
    - Low overnight (11pm-5am): ~150W base load
    - Morning peak (6am-9am): ~400W
    - Daytime moderate (9am-5pm): ~250W
    - Evening peak (5pm-10pm): ~500W
    """
    return create_realistic_load_profile()


# ─── Helper Factory Functions ────────────────────────────────────────────────
# These are exposed as module-level functions so tests can call them directly
# with custom parameters when fixtures don't provide enough flexibility.


def create_simulation_params(**overrides) -> SimulationInput:
    """
    Create SimulationInput with sensible defaults.
    
    This is the primary factory function for creating test simulation inputs.
    All default values are chosen to represent a typical residential PV system.
    
    Keyword arguments use the canonical field names from the sub-configs:
    
    ConsumptionConfig fields:
        profile_mode, annual_kwh, active_base, profile_saturday, profile_sunday,
        yearly_profile, seasonal_enabled, season_winter_pct, season_summer_pct,
        flex_enabled, flex_delta, flex_min_yield, flex_pool, flex_refresh,
        periodic_enabled, periodic_delta, periodic_days
    
    StorageConfig fields:
        dc_coupled, batt_loss, min_soc_summer, max_soc_summer,
        min_soc_winter, max_soc_winter
    
    SimulationInput fields:
        data_year, inverter_limit_kw, inverter_efficiency_curve,
        batt_inverter_efficiency_curve
    
    Args:
        **overrides: Keyword arguments to override default parameter values.
        
    Returns:
        SimulationInput with defaults merged with overrides.
    """

    def get(key, default):
        return overrides.get(key, default)

    consumption = ConsumptionConfig(
        profile_mode=get('profile_mode', 'Erweitert'),
        annual_kwh=get('annual_kwh', 3000),
        active_base=get('active_base', [200] * 24),
        profile_saturday=get('profile_saturday', None),
        profile_sunday=get('profile_sunday', None),
        yearly_profile=get('yearly_profile', None),
        seasonal_enabled=get('seasonal_enabled', False),
        season_winter_pct=get('season_winter_pct', 100),
        season_summer_pct=get('season_summer_pct', 100),
        flex_enabled=get('flex_enabled', False),
        flex_delta=get('flex_delta', [0] * 24),
        flex_min_yield=get('flex_min_yield', 5.0),
        flex_pool=get('flex_pool', 3),
        flex_refresh=get('flex_refresh', 0.5),
        periodic_enabled=get('periodic_enabled', False),
        periodic_delta=get('periodic_delta', [0] * 24),
        periodic_days=get('periodic_days', 3),
        min_load_w_override=get('min_load_w_override', None),
    )

    storage = StorageConfig(
        dc_coupled=get('dc_coupled', True),
        batt_loss=get('batt_loss', 10),
        min_soc_summer=get('min_soc_summer', 10),
        max_soc_summer=get('max_soc_summer', 100),
        min_soc_winter=get('min_soc_winter', 20),
        max_soc_winter=get('max_soc_winter', 100),
    )

    return SimulationInput(
        consumption=consumption,
        storage=storage,
        data_year=get('data_year', 2015),
        inverter_limit_kw=get('inverter_limit_kw', 0.8),
        inverter_efficiency_curve=get(
            'inverter_efficiency_curve', INVERTER_EFFICIENCY_CURVES["median"]
        ),
        batt_inverter_efficiency_curve=get(
            'batt_inverter_efficiency_curve', INVERTER_EFFICIENCY_CURVES["median"]
        ),
        discharge_strategy_config=get(
            'discharge_strategy_config', DischargeStrategyConfig()
        ),
    )


def create_constant_pv(power_kw: float, hours: int = 8760) -> np.ndarray:
    """
    Create constant PV generation array.
    
    Args:
        power_kw: Constant power output in kW.
        hours: Number of hours (default 8760 for one year).
        
    Returns:
        NumPy array with constant power values.
    """
    return np.full(hours, power_kw)


def create_daytime_pv(peak_kw: float = 1.0, hours: int = 8760) -> np.ndarray:
    """
    Create PV array with generation only during daytime hours (6-18).
    
    Args:
        peak_kw: Power output during daytime hours in kW.
        hours: Number of hours (default 8760 for one year).
        
    Returns:
        NumPy array with power during daytime, zero at night.
    """
    pv = np.zeros(hours)
    for i in range(hours):
        hour = i % 24
        if 6 <= hour < 18:
            pv[i] = peak_kw
    return pv


def create_synthetic_pv_data(
        hours: int = 8760,
        peak_power_kw: float = 2.0,
        seed: int = 42,
) -> np.ndarray:
    """
    Create realistic synthetic PV generation data with daily and seasonal patterns.
    
    Generates data simulating a real PV system with:
    - Bell curve daily pattern (peak at noon)
    - Seasonal variation (more in summer, less in winter)
    - Optional random noise for variability
    
    Args:
        hours: Number of hours to simulate (default: 8760 = 1 year).
        peak_power_kw: Peak power in kW at summer noon (default: 2.0 kW).
        seed: Random seed for reproducibility (default: 42).
        
    Returns:
        NumPy array with synthetic PV generation data.
    """
    pv_data = np.zeros(hours)

    for i in range(hours):
        hour = i % 24
        day = i // 24

        # Calculate day of year (1-365)
        day_of_year = day % 365 + 1

        # Seasonal factor: peaks in summer (day ~172), lowest in winter
        seasonal_factor = 0.5 + 0.5 * np.sin(2 * np.pi * (day_of_year - 80) / 365)

        # Daily pattern: bell curve centered at noon
        if 5 <= hour <= 20:
            # Hours from solar noon (12)
            hours_from_noon = abs(hour - 12.5)
            # Gaussian-like curve
            daily_factor = np.exp(-0.3 * hours_from_noon ** 2)

            # Peak power scaled by season
            pv_data[i] = peak_power_kw * seasonal_factor * daily_factor
        else:
            pv_data[i] = 0.0

    return pv_data


def create_realistic_load_profile() -> list[float]:
    """
    Create a realistic daily load profile in Watts.
    
    Pattern represents typical German household consumption:
    - Low overnight (11pm-5am): ~150W base load (refrigerator, standby)
    - Morning peak (6am-9am): ~400W (breakfast, getting ready)
    - Daytime moderate (9am-5pm): ~250W (lights, appliances)
    - Evening peak (5pm-10pm): ~500W (cooking, TV, activities)
    
    Returns:
        List of 24 float values representing hourly load in Watts.
    """
    return [
        150, 150, 150, 150, 150, 150,  # 00:00-05:59: Night
        300, 400, 450, 300,  # 06:00-09:59: Morning
        250, 250, 300, 250, 250, 250,  # 10:00-15:59: Daytime
        350, 500, 550, 500, 450, 350,  # 16:00-21:59: Evening
        200, 150,  # 22:00-23:59: Late evening
    ]
