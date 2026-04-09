"""
Data classes for the PV analysis application.
Provides type-safe configuration and result structures.
"""
from dataclasses import dataclass, field

from solarbatteryield.simulation.inverter_efficiency import (
    DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT,
    DEFAULT_INVERTER_EFFICIENCY_CURVE,
    INVERTER_EFFICIENCY_CURVES,
)


@dataclass(frozen=True, slots=True)
class HourlyResult:
    """Result of processing a single simulation hour."""
    grid_import: float
    feed_in: float
    curtailed: float
    direct_pv: float
    battery_discharge: float
    pv_generation: float
    consumption: float


@dataclass(frozen=True, slots=True)
class HourlySoCData:
    """Hourly state of charge and PV generation data for detailed analysis."""
    hour: int  # Hour index within the week (0-167)
    soc: float  # State of charge in kWh
    soc_pct: float  # State of charge as percentage (0-100)
    pv_generation: float  # PV generation in kWh
    consumption: float  # Consumption in kWh


@dataclass
class WeeklyHourlyData:
    """
    Hourly data for a representative week (168 hours).
    Used for SoC visualization in summer vs winter comparison.
    """
    hours: list[HourlySoCData] = field(default_factory=list)
    
    def add_hour(self, hour: int, soc: float, soc_pct: float, 
                 pv_generation: float, consumption: float) -> None:
        """Add data for one hour."""
        self.hours.append(HourlySoCData(
            hour=hour, soc=soc, soc_pct=soc_pct,
            pv_generation=pv_generation, consumption=consumption
        ))


@dataclass
class PVModule:
    """Configuration for a single PV module/panel."""
    id: int
    name: str
    peak: float  # Peak power in kWp
    azi: int  # Azimuth angle (0=South, 90=West, -90=East)
    slope: int  # Tilt angle in degrees (0=horizontal, 90=vertical)


@dataclass
class StorageOption:
    """Configuration for a battery storage option."""
    id: int
    name: str
    cap: float  # Capacity in kWh
    cost: int  # Additional cost over base system in EUR


@dataclass
class LocationConfig:
    """Geographic location configuration."""
    lat: float | None = None
    lon: float | None = None
    
    def __post_init__(self) -> None:
        """Validate location coordinates."""
        if self.lat is not None:
            if not -90 <= self.lat <= 90:
                raise ValueError(f"Breitengrad muss zwischen -90 und 90 liegen, war {self.lat}")
        if self.lon is not None:
            if not -180 <= self.lon <= 180:
                raise ValueError(f"Längengrad muss zwischen -180 und 180 liegen, war {self.lon}")


@dataclass
class ConsumptionConfig:
    """Household consumption configuration."""
    profile_mode: str = "Einfach"  # "Einfach", "Erweitert", or "Experte"
    annual_kwh: float | None = None
    
    # Load profiles (in Watts for each hour 0-23)
    # In simple mode: H0 profile is used, these are ignored
    # In advanced mode: user provides these profiles
    active_base: list[int] = field(default_factory=lambda: [0] * 24)
    
    # Optional separate profiles for different day types (advanced mode only)
    # If None, active_base is used for all days
    profile_saturday: list[int] | None = None
    profile_sunday: list[int] | None = None
    
    # Full year hourly profile (expert mode only)
    # Contains hourly consumption in Watts for the entire year (8760 or 8784 values)
    yearly_profile: list[float] | None = None
    
    # Seasonal scaling (only used in advanced mode)
    seasonal_enabled: bool = True
    season_winter_pct: int = 114  # Winter factor (%)
    season_summer_pct: int = 86   # Summer factor (%)
    
    # Flexible load shifting (sunny days)
    flex_enabled: bool = False
    flex_delta: list[int] = field(default_factory=lambda: [0] * 24)
    flex_min_yield: float = 5.0  # Minimum daily yield to trigger (kWh)
    flex_pool: int = 3  # Max uses in pool
    flex_refresh: float = 0.5  # Refresh rate per day
    
    # Periodic load (regular interval)
    periodic_enabled: bool = False
    periodic_delta: list[int] = field(default_factory=lambda: [0] * 24)
    periodic_days: int = 3  # Interval in days
    
    def has_day_type_profiles(self) -> bool:
        """Check if separate day-type profiles are provided."""
        return self.profile_saturday is not None and self.profile_sunday is not None
    
    def has_yearly_profile(self) -> bool:
        """Check if a full year hourly profile is provided (expert mode)."""
        return self.yearly_profile is not None and len(self.yearly_profile) > 0


@dataclass
class PVSystemConfig:
    """PV system configuration."""
    data_year: int = 2015
    system_loss: int = 9  # System losses in % (DC-side only, excludes inverter losses)
    inverter_limit_enabled: bool = True
    inverter_limit_w: int = 800  # Inverter limit in Watts
    base_cost: int = 800  # Base system cost in EUR
    modules: list[PVModule] = field(default_factory=list)
    
    # Inverter efficiency curve selection
    # Options: "pessimistic", "median", "optimistic", "custom"
    inverter_efficiency_preset: str = "median"
    
    # Custom efficiency curve (used when inverter_efficiency_preset == "custom")
    # Format: list of efficiency values (0-100%) at power levels [10%, 20%, 30%, 50%, 75%, 100%]
    inverter_efficiency_custom: list[float] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Initialize custom efficiency with P50 defaults if empty."""
        if not self.inverter_efficiency_custom:
            self.inverter_efficiency_custom = list(DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT)


@dataclass
class StorageConfig:
    """Battery storage configuration."""
    dc_coupled: bool = True
    batt_loss: int = 7  # Cell charge/discharge loss in % (excludes inverter losses)
    min_soc_summer: int = 10  # Min. SoC summer in %
    max_soc_summer: int = 100  # Max. SoC summer in %
    min_soc_winter: int = 20  # Min. SoC winter in %
    max_soc_winter: int = 100  # Max. SoC winter in %
    options: list[StorageOption] = field(default_factory=list)
    
    # Battery inverter efficiency (AC-coupled only)
    # The battery's own bidirectional inverter for AC/DC conversion
    # Options: "pessimistic", "median", "optimistic", "custom"
    batt_inverter_preset: str = "median"
    batt_inverter_efficiency_custom: list[float] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate storage configuration and initialize defaults."""
        if not 0 <= self.batt_loss <= 50:
            raise ValueError(f"Batterieverluste müssen zwischen 0% und 50% liegen, war {self.batt_loss}%")
        
        if not self.batt_inverter_efficiency_custom:
            self.batt_inverter_efficiency_custom = list(DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT)
        
        for season, min_soc, max_soc in [
            ("Sommer", self.min_soc_summer, self.max_soc_summer),
            ("Winter", self.min_soc_winter, self.max_soc_winter),
        ]:
            if not 0 <= min_soc <= 100:
                raise ValueError(f"Min. SoC {season} muss zwischen 0% und 100% liegen")
            if not 0 <= max_soc <= 100:
                raise ValueError(f"Max. SoC {season} muss zwischen 0% und 100% liegen")
            if min_soc > max_soc:
                raise ValueError(f"Min. SoC {season} ({min_soc}%) darf nicht größer als Max. SoC ({max_soc}%) sein")


@dataclass
class EconomicsConfig:
    """Economic parameters for analysis."""
    e_price: float = 0.27  # Electricity price in EUR/kWh
    e_inc: float = 0.03  # Annual price increase (decimal)
    feed_in_tariff: float = 0.0  # Feed-in tariff in ct/kWh
    etf_ret: float = 0.07  # Annual ETF return (decimal)
    reinvest_savings: bool = False  # Reinvest PV savings with ETF return rate
    analysis_years: int = 15  # Analysis horizon in years

    def __post_init__(self) -> None:
        """Validate economic parameters."""
        if self.e_price <= 0:
            raise ValueError(f"Strompreis muss positiv sein, war {self.e_price} €/kWh")
        if not 1 <= self.analysis_years <= 50:
            raise ValueError(f"Analysezeitraum muss zwischen 1 und 50 Jahren liegen, war {self.analysis_years}")


@dataclass
class SimulationInput:
    """
    Input data for running a simulation.
    
    Composes ConsumptionConfig and StorageConfig by reference instead of
    copying their fields, plus a few pre-computed values derived from
    PVSystemConfig.
    """
    consumption: ConsumptionConfig
    storage: StorageConfig
    data_year: int
    inverter_limit_kw: float | None
    inverter_efficiency_curve: tuple[tuple[int, float], ...]
    batt_inverter_efficiency_curve: tuple[tuple[int, float], ...]
    
    def use_h0_profile(self) -> bool:
        """Check if H0 standard profile should be used."""
        return self.consumption.profile_mode == "Einfach"
    
    def use_yearly_profile(self) -> bool:
        """Check if full year hourly profile should be used (expert mode)."""
        return (self.consumption.profile_mode == "Experte"
                and self.consumption.has_yearly_profile())
    
    def has_day_type_profiles(self) -> bool:
        """Check if separate day-type profiles are provided."""
        return self.consumption.has_day_type_profiles()


@dataclass
class SimulationConfig:
    """Complete simulation configuration combining all settings."""
    location: LocationConfig = field(default_factory=LocationConfig)
    consumption: ConsumptionConfig = field(default_factory=ConsumptionConfig)
    pv_system: PVSystemConfig = field(default_factory=PVSystemConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    economics: EconomicsConfig = field(default_factory=EconomicsConfig)
    
    @property
    def lat(self) -> float | None:
        return self.location.lat
    
    @property
    def lon(self) -> float | None:
        return self.location.lon
    
    @property
    def inverter_limit_kw(self) -> float | None:
        """Get inverter limit in kW, or None if disabled."""
        if self.pv_system.inverter_limit_enabled:
            return self.pv_system.inverter_limit_w / 1000
        return None
    
    @property
    def feed_in_tariff_eur(self) -> float:
        """Get feed-in tariff in EUR/kWh."""
        return self.economics.feed_in_tariff / 100
    
    @property
    def total_peak_kwp(self) -> float:
        """Get total peak power of all modules."""
        return sum(m.peak for m in self.pv_system.modules)
    
    @staticmethod
    def _build_efficiency_curve(
        preset: str,
        custom_values: list[float] | None = None,
    ) -> tuple[tuple[int, float], ...]:
        """
        Build an efficiency curve from preset name or custom values.
        
        Args:
            preset: One of "pessimistic", "median", "optimistic", or "custom"
            custom_values: List of efficiency percentages at power levels [10%, 20%, 30%, 50%, 75%, 100%]
        
        Returns:
            Tuple of (power_level_percent, efficiency) pairs.
        """
        if preset == "custom" and custom_values:
            power_levels = [10, 20, 30, 50, 75, 100]
            return tuple(
                (level, eff / 100)
                for level, eff in zip(power_levels, custom_values)
            )
        elif preset in INVERTER_EFFICIENCY_CURVES:
            return INVERTER_EFFICIENCY_CURVES[preset]
        else:
            return DEFAULT_INVERTER_EFFICIENCY_CURVE
    
    def get_inverter_efficiency_curve(self) -> tuple[tuple[int, float], ...]:
        """Get the PV inverter efficiency curve based on preset or custom values."""
        return self._build_efficiency_curve(
            self.pv_system.inverter_efficiency_preset,
            self.pv_system.inverter_efficiency_custom,
        )
    
    def get_batt_inverter_efficiency_curve(self) -> tuple[tuple[int, float], ...]:
        """
        Get the battery inverter efficiency curve (AC-coupled only).
        
        For DC-coupled systems this curve is not used in simulation, but we
        still return a valid curve for consistency.
        """
        return self._build_efficiency_curve(
            self.storage.batt_inverter_preset,
            self.storage.batt_inverter_efficiency_custom,
        )
    
    def is_valid(self) -> tuple[bool, list[str]]:
        """Check if configuration is valid for simulation."""
        missing = []
        if self.location.lat is None or self.location.lon is None:
            missing.append("📍 **Standort** – Breitengrad und Längengrad eingeben oder Ort suchen")
        if self.consumption.profile_mode == "Einfach" and self.consumption.annual_kwh is None:
            missing.append("💡 **Jahresverbrauch** – jährlichen Stromverbrauch in kWh angeben")
        if self.consumption.profile_mode == "Experte" and not self.consumption.has_yearly_profile():
            missing.append("📊 **Jahreslastprofil** – CSV-Datei mit stündlichen Verbrauchsdaten hochladen")
        return len(missing) == 0, missing
    
    def to_simulation_input(self) -> SimulationInput:
        """Create SimulationInput from this config."""
        return SimulationInput(
            consumption=self.consumption,
            storage=self.storage,
            data_year=self.pv_system.data_year,
            inverter_limit_kw=self.inverter_limit_kw,
            inverter_efficiency_curve=self.get_inverter_efficiency_curve(),
            batt_inverter_efficiency_curve=self.get_batt_inverter_efficiency_curve(),
        )


@dataclass
class MonthlyData:
    """Monthly energy flow data."""
    direct_pv: float = 0.0  # Direct PV consumption in kWh
    battery: float = 0.0  # Battery discharge in kWh
    grid_import: float = 0.0  # Grid import in kWh
    feed_in: float = 0.0  # Grid feed-in in kWh
    consumption: float = 0.0  # Total consumption in kWh
    pv_generation: float = 0.0  # Total PV generation in kWh
    
    def add_hourly_result(self, result: HourlyResult) -> None:
        """
        Add hourly simulation result values to monthly totals.
        
        Args:
            result: The hourly simulation result to accumulate
        """
        self.direct_pv += result.direct_pv
        self.battery += result.battery_discharge
        self.grid_import += result.grid_import
        self.feed_in += result.feed_in
        self.pv_generation += result.pv_generation
        self.consumption += result.consumption


@dataclass
class SimulationResult:
    """Result of a single simulation run."""
    grid_import: float  # Total grid import (kWh)
    total_consumption: float  # Total consumption (kWh)
    feed_in: float  # Total feed-in (kWh)
    curtailed: float  # Total curtailed energy (kWh)
    monthly: dict[int, MonthlyData]  # Monthly breakdown
    full_cycles: float = 0.0  # Number of full battery cycles per year
    
    # Weekly SoC data for detailed visualization (optional)
    # First week of July (summer), January (winter), and April (transition)
    weekly_summer: WeeklyHourlyData | None = None
    weekly_winter: WeeklyHourlyData | None = None
    weekly_transition: WeeklyHourlyData | None = None


@dataclass
class ScenarioResult:
    """Results for a single simulation scenario."""
    name: str
    storage_capacity: float  # Battery capacity in kWh
    investment_cost: float  # Total investment in EUR
    simulation: SimulationResult  # Simulation results
    
    # Delegate energy values to simulation
    @property
    def grid_import(self) -> float:
        return self.simulation.grid_import
    
    @property
    def total_consumption(self) -> float:
        return self.simulation.total_consumption
    
    @property
    def feed_in(self) -> float:
        return self.simulation.feed_in
    
    @property
    def curtailed(self) -> float:
        return self.simulation.curtailed
    
    @property
    def monthly(self) -> dict[int, MonthlyData]:
        return self.simulation.monthly
    
    @property
    def full_cycles(self) -> float:
        return self.simulation.full_cycles
    
    @property
    def autarky(self) -> float:
        """Calculate autarky percentage."""
        if self.total_consumption > 0:
            return (1 - self.grid_import / self.total_consumption) * 100
        return 0.0
    
    @property
    def self_consumption(self) -> float:
        """Calculate self-consumption percentage."""
        pv_generation = self.feed_in + self.curtailed + (self.total_consumption - self.grid_import)
        if pv_generation > 0:
            self_consumed = pv_generation - self.feed_in - self.curtailed
            return (self_consumed / pv_generation) * 100
        return 0.0
    
    @property
    def saved_kwh(self) -> float:
        """Calculate saved energy from grid."""
        return self.total_consumption - self.grid_import
    
    def annual_savings(self, e_price: float, feed_in_tariff: float) -> float:
        """Calculate annual savings in EUR."""
        return self.saved_kwh * e_price + self.feed_in * feed_in_tariff


@dataclass
class AnalysisResult:
    """Collection of all scenario results."""
    scenarios: list[ScenarioResult] = field(default_factory=list)
    pv_generation_total: float = 0.0  # Total PV generation in kWh
    
    @property
    def total_consumption(self) -> float:
        """Get total consumption (same for all scenarios)."""
        if self.scenarios:
            return self.scenarios[0].total_consumption
        return 0.0
    
    def get_best_scenario(self, e_price: float, e_inc: float, 
                          feed_in_tariff: float, years: int) -> ScenarioResult:
        """Find the scenario with highest profit over the analysis period."""
        def calculate_profit(s: ScenarioResult) -> float:
            total_savings = sum(
                s.saved_kwh * e_price * (1 + e_inc) ** y + s.feed_in * feed_in_tariff
                for y in range(years)
            )
            return total_savings - s.investment_cost
        
        return max(self.scenarios, key=calculate_profit)
