"""
Configuration constants and default values for the PV analysis application.
All default values are centralized here as a single source of truth.
"""
from dataclasses import dataclass, field
from typing import Any

from h0_profile import H0_TRANSITION, get_season, Season
from datetime import date


# ─── Default consumption profiles (Watt per hour 0–23) ─────────
# Derived from the BDEW H0 transition (Übergangszeit) profile, which serves as
# the neutral baseline for seasonal scaling (100% factor). Separate profiles for
# weekday, Saturday, and Sunday/holiday allow day-type differentiation.
#
# The scale factor is chosen so that the profile gives ~3000 kWh/year when
# combined with the default seasonal scaling (Winter 114%, Summer 86%).
# Winter has more days (140) than summer (123), so without correction the
# asymmetric scaling would push the total above 3000 kWh.
def _compute_profile_scale(target_kwh: float = 3000.0, year: int = 2015,
                           winter_pct: int = 114, summer_pct: int = 86) -> float:
    """Compute scale factor for transition profile to hit target_kwh with seasonal scaling."""
    start = date(year, 1, 1)
    days = 366 if year % 4 == 0 else 365
    base_kwh_day = sum(H0_TRANSITION.weekday.values) / 1000
    weighted_days = 0.0
    for d in range(days):
        cur = date.fromordinal(start.toordinal() + d)
        season = get_season(cur.month, cur.day)
        if season == Season.WINTER:
            weighted_days += winter_pct / 100
        elif season == Season.SUMMER:
            weighted_days += summer_pct / 100
        else:
            weighted_days += 1.0
    return target_kwh / (base_kwh_day * weighted_days)

_PROFILE_SCALE: float = _compute_profile_scale()

PROFILE_BASE: list[int] = [round(v * _PROFILE_SCALE) for v in H0_TRANSITION.weekday.values]
PROFILE_SATURDAY: list[int] = [round(v * _PROFILE_SCALE) for v in H0_TRANSITION.saturday.values]
PROFILE_SUNDAY: list[int] = [round(v * _PROFILE_SCALE) for v in H0_TRANSITION.sunday.values]

# Reference annual consumption that the default profiles are calibrated for.
# With default seasonal scaling (114/86), PROFILE_BASE gives exactly this amount.
TARGET_ANNUAL_KWH: float = 3000.0

DEFAULT_ANNUAL_KWH: float = sum(PROFILE_BASE) / 1000 * 365


def scale_profiles(annual_kwh: float) -> tuple[list[int], list[int], list[int]]:
    """
    Scale all default profiles to match a target annual consumption.

    The returned profiles will yield approximately `annual_kwh` when used
    with the default seasonal scaling factors (114% winter, 86% summer).

    Returns:
        Tuple of (weekday, saturday, sunday) profiles in Watts per hour.
    """
    ratio = annual_kwh / TARGET_ANNUAL_KWH
    return (
        [round(v * ratio) for v in PROFILE_BASE],
        [round(v * ratio) for v in PROFILE_SATURDAY],
        [round(v * ratio) for v in PROFILE_SUNDAY],
    )

FLEX_DELTA_DEFAULT: list[int] = [0] * 24

PERIODIC_DELTA_DEFAULT: list[int] = [0] * 24

MONTH_LABELS: list[str] = [
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"
]

# ─── Default module configuration ──────────────────────────────
DEFAULT_MODULES: list[dict[str, Any]] = [
    {"id": 0, "name": "Süd", "peak": 2.0, "azi": 0, "slope": 60},
]

# ─── Default storage configurations ────────────────────────────
DEFAULT_STORAGES: list[dict[str, Any]] = [
    {"id": 0, "name": "Klein", "cap": 2.0, "cost": 700},
    {"id": 1, "name": "Mittel", "cap": 4.0, "cost": 1100},
    {"id": 2, "name": "Groß", "cap": 6.0, "cost": 1500},
]


# ─── Centralized Default Values ────────────────────────────────
@dataclass(frozen=True)
class ConfigDefaults:
    """
    All configuration default values in one place.
    Use this as the single source of truth for defaults.
    """
    # Location
    lat: float | None = None
    lon: float | None = None
    
    # Consumption
    # Profile modes: "Einfach" (H0), "Erweitert" (custom daily), "Experte" (full year CSV)
    profile_mode: str = "Einfach"
    annual_kwh: float | None = None
    seasonal_enabled: bool = True
    season_winter: int = 114  # Winter factor % (H0 ideal: 113.85%)
    season_summer: int = 86   # Summer factor % (H0 ideal: 85.54%)
    
    # Flexible load
    flex_enabled: bool = False
    flex_min_yield: float = 5.0  # kWh
    flex_pool: int = 3
    flex_refresh: float = 0.5
    
    # Periodic load
    periodic_enabled: bool = False
    periodic_days: int = 3
    
    # PV System
    year: int = 2015
    loss: int = 12  # System losses %
    inverter_efficiency_preset: str = "median"  # "pessimistic", "median", "optimistic", "custom"
    inverter_limit_enabled: bool = True
    inverter_limit_w: int = 800  # Watts
    base_cost: int = 800  # EUR
    
    # Storage
    dc_coupled: str = "DC-gekoppelt"
    batt_loss: int = 10  # Charge/discharge loss %
    min_soc_summer: int = 10  # Min SoC summer %
    max_soc_summer: int = 100  # Max SoC summer %
    min_soc_winter: int = 20  # Min SoC winter %
    max_soc_winter: int = 100  # Max SoC winter %
    
    # Economics
    e_price: float = 0.27  # EUR/kWh
    e_inc: float = 3.0  # % per year
    feed_in_tariff: float = 0.0  # ct/kWh
    etf_ret: float = 7.0  # % per year
    years: int = 15  # Analysis horizon


# Singleton instance for easy access
DEFAULTS = ConfigDefaults()


# ─── Session State Key Mappings ────────────────────────────────────────────────
# Maps session state keys to their default values from ConfigDefaults
SESSION_STATE_DEFAULTS: dict[str, Any] = {
    "cfg_lat": DEFAULTS.lat,
    "cfg_lon": DEFAULTS.lon,
    "cfg_profile_mode": DEFAULTS.profile_mode,
    "cfg_annual_kwh": DEFAULTS.annual_kwh,
    "cfg_seasonal_enabled": DEFAULTS.seasonal_enabled,
    "cfg_season_winter": DEFAULTS.season_winter,
    "cfg_season_summer": DEFAULTS.season_summer,
    "cfg_flex_enabled": DEFAULTS.flex_enabled,
    "cfg_flex_min_yield": DEFAULTS.flex_min_yield,
    "cfg_flex_pool": DEFAULTS.flex_pool,
    "cfg_flex_refresh": DEFAULTS.flex_refresh,
    "cfg_periodic_enabled": DEFAULTS.periodic_enabled,
    "cfg_periodic_days": DEFAULTS.periodic_days,
    "cfg_year": DEFAULTS.year,
    "cfg_loss": DEFAULTS.loss,
    "cfg_inverter_efficiency_preset": DEFAULTS.inverter_efficiency_preset,
    "cfg_inverter_limit_enabled": DEFAULTS.inverter_limit_enabled,
    "cfg_inverter_limit_w": DEFAULTS.inverter_limit_w,
    "cfg_base_cost": DEFAULTS.base_cost,
    "cfg_dc_coupled": DEFAULTS.dc_coupled,
    "cfg_batt_loss": DEFAULTS.batt_loss,
    "cfg_min_soc_s": DEFAULTS.min_soc_summer,
    "cfg_max_soc_s": DEFAULTS.max_soc_summer,
    "cfg_min_soc_w": DEFAULTS.min_soc_winter,
    "cfg_max_soc_w": DEFAULTS.max_soc_winter,
    "cfg_e_price": DEFAULTS.e_price,
    "cfg_e_inc": DEFAULTS.e_inc,
    "cfg_feed_in_tariff": DEFAULTS.feed_in_tariff,
    "cfg_etf_ret": DEFAULTS.etf_ret,
    "cfg_years": DEFAULTS.years,
}

# ─── Config keys for URL sharing ───────────────────────────────
CONFIG_KEYS_SIMPLE: list[str] = list(SESSION_STATE_DEFAULTS.keys())

# Keys that need persistence when widgets are collapsed
PERSISTED_KEYS: list[str] = [
    "cfg_lat", "cfg_lon", "cfg_profile_mode", "cfg_annual_kwh",
    "cfg_flex_enabled", "cfg_flex_min_yield", "cfg_flex_pool", "cfg_flex_refresh",
    "cfg_periodic_enabled", "cfg_periodic_days",
    "cfg_seasonal_enabled", "cfg_season_winter", "cfg_season_summer",
    "cfg_year", "cfg_loss", "cfg_inverter_limit_enabled", "cfg_inverter_limit_w",
    "cfg_base_cost", "cfg_dc_coupled", "cfg_inverter_efficiency_preset",
    "cfg_batt_loss", "cfg_min_soc_s", "cfg_max_soc_s", "cfg_min_soc_w", "cfg_max_soc_w",
    "cfg_e_price", "cfg_e_inc", "cfg_feed_in_tariff", "cfg_etf_ret", "cfg_years",
]


# ─── Input Validation Limits ───────────────────────────────────
@dataclass(frozen=True)
class ValidationLimits:
    """Validation limits for user inputs."""
    # Coordinates
    lat_min: float = -90.0
    lat_max: float = 90.0
    lon_min: float = -180.0
    lon_max: float = 180.0
    
    # Consumption
    annual_kwh_min: int = 100
    annual_kwh_max: int = 100_000
    
    # PV System
    year_min: int = 2005
    year_max: int = 2023
    loss_min: int = 0
    loss_max: int = 30
    inverter_eff_min: int = 80
    inverter_eff_max: int = 100
    inverter_limit_w_min: int = 100
    inverter_limit_w_max: int = 100_000
    
    # Storage
    batt_loss_min: int = 0
    batt_loss_max: int = 30
    soc_min: int = 0
    soc_max: int = 100
    
    # Economics
    e_price_min: float = 0.01
    e_price_max: float = 1.0
    e_inc_min: float = -5.0
    e_inc_max: float = 20.0
    etf_ret_min: float = -10.0
    etf_ret_max: float = 30.0
    years_min: int = 1
    years_max: int = 50


LIMITS = ValidationLimits()


# ─── UI Color Scheme ───────────────────────────────────────────
@dataclass(frozen=True)
class ColorScheme:
    """Color definitions for charts and styling."""
    # Status colors
    positive: str = "#4caf50"  # Green
    warning: str = "#ff9800"   # Orange
    negative: str = "#e53935"  # Red
    
    # Chart colors
    direct_pv: str = "#ff9800"    # Orange
    battery: str = "#4db68a"      # Teal
    grid_import: str = "#488fc2"  # Blue
    feed_in: str = "#a280db"      # Purple
    consumption_line: str = "#78909c"  # Gray
    
    # Thresholds for coloring
    autarky_good: float = 50.0
    autarky_medium: float = 30.0
    self_consumption_good: float = 70.0
    self_consumption_medium: float = 50.0
    yield_good: float = 15.0
    yield_medium: float = 8.0
    amortization_good: float = 5.0
    amortization_medium: float = 10.0
    
    # Full cycles thresholds (per year)
    # < 150: Low utilization (battery likely oversized)
    # 150-300: Optimal range (good balance, ~0.4-0.8 cycles/day)
    # > 300: High utilization (faster aging, rare in practice)
    cycles_low: float = 150.0
    cycles_high: float = 300.0


COLORS = ColorScheme()
