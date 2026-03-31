"""
Configuration constants and default values for the PV analysis application.
All default values are centralized here as a single source of truth.
"""
from dataclasses import dataclass, field
from typing import Any


# ─── Default consumption profiles (Watt per hour 0–23) ─────────
# BDEW H0 Standardlastprofil (Haushalt), Jahresdurchschnitt über alle Monate,
# normiert auf ca. 3000 kWh/Jahr (durchschnittlicher deutscher Haushalt).
PROFILE_BASE: list[int] = [
    209, 156, 135, 129, 130, 148,     # 00-05: Nacht (Grundlast)
    239, 335, 388, 416, 425, 445,     # 06-11: Morgen (Frühstück, Arbeitsbeginn)
    481, 454, 394, 355, 342, 389,     # 12-17: Mittag/Nachmittag
    475, 537, 504, 444, 390, 298,     # 18-23: Abend (Hauptverbrauchszeit)
]
DEFAULT_ANNUAL_KWH: float = sum(PROFILE_BASE) / 1000 * 365  # ≈ 3000 kWh/a

FLEX_DELTA_DEFAULT: list[int] = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 110, 160, 0, 0, 410, 530, 0, 0, 0, 0, 0, 0, 0,
]

PERIODIC_DELTA_DEFAULT: list[int] = [
    350, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
]

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
    profile_mode: str = "Einfach"
    annual_kwh: float | None = None
    seasonal_enabled: bool = True
    season_winter: int = 114  # Winter factor %
    season_summer: int = 87   # Summer factor %
    
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
    inverter_eff: int = 96  # Inverter efficiency %
    inverter_limit_enabled: bool = True
    inverter_limit_w: int = 800  # Watts
    feed_in_tariff: float = 0.0  # ct/kWh
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
    etf_ret: float = 7.0  # % per year
    years: int = 15  # Analysis horizon


# Singleton instance for easy access
DEFAULTS = ConfigDefaults()


# ─── Session State Key Mappings ────────────────────────────────
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
    "cfg_inverter_eff": DEFAULTS.inverter_eff,
    "cfg_inverter_limit_enabled": DEFAULTS.inverter_limit_enabled,
    "cfg_inverter_limit_w": DEFAULTS.inverter_limit_w,
    "cfg_feed_in_tariff": DEFAULTS.feed_in_tariff,
    "cfg_base_cost": DEFAULTS.base_cost,
    "cfg_dc_coupled": DEFAULTS.dc_coupled,
    "cfg_batt_loss": DEFAULTS.batt_loss,
    "cfg_min_soc_s": DEFAULTS.min_soc_summer,
    "cfg_max_soc_s": DEFAULTS.max_soc_summer,
    "cfg_min_soc_w": DEFAULTS.min_soc_winter,
    "cfg_max_soc_w": DEFAULTS.max_soc_winter,
    "cfg_e_price": DEFAULTS.e_price,
    "cfg_e_inc": DEFAULTS.e_inc,
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
    "cfg_feed_in_tariff", "cfg_base_cost", "cfg_dc_coupled", "cfg_inverter_eff",
    "cfg_batt_loss", "cfg_min_soc_s", "cfg_max_soc_s", "cfg_min_soc_w", "cfg_max_soc_w",
    "cfg_e_price", "cfg_e_inc", "cfg_etf_ret", "cfg_years",
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


COLORS = ColorScheme()
