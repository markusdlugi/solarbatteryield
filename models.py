"""
Data classes for the PV analysis application.
Provides type-safe configuration and result structures.
"""
from dataclasses import dataclass, field


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
    profile_mode: str = "Einfach"  # "Einfach" or "Erweitert"
    annual_kwh: float | None = None
    active_base: list[int] = field(default_factory=lambda: [0] * 24)
    
    # Seasonal scaling
    seasonal_enabled: bool = True
    season_winter_pct: int = 114  # Winter factor (%)
    season_summer_pct: int = 87   # Summer factor (%)
    
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


@dataclass
class PVSystemConfig:
    """PV system configuration."""
    data_year: int = 2015
    system_loss: int = 12  # System losses in %
    inverter_eff: int = 96  # Inverter efficiency in %
    inverter_limit_enabled: bool = True
    inverter_limit_w: int = 800  # Inverter limit in Watts
    feed_in_tariff: float = 0.0  # Feed-in tariff in ct/kWh
    base_cost: int = 800  # Base system cost in EUR
    modules: list[PVModule] = field(default_factory=list)


@dataclass
class StorageConfig:
    """Battery storage configuration."""
    dc_coupled: bool = True
    batt_loss: int = 10  # Charge/discharge loss in %
    min_soc_summer: int = 10  # Min SoC summer in %
    max_soc_summer: int = 100  # Max SoC summer in %
    min_soc_winter: int = 20  # Min SoC winter in %
    max_soc_winter: int = 100  # Max SoC winter in %
    options: list[StorageOption] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate storage configuration."""
        if not 0 <= self.batt_loss <= 50:
            raise ValueError(f"Batterieverluste müssen zwischen 0% und 50% liegen, war {self.batt_loss}%")
        
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
    etf_ret: float = 0.07  # Annual ETF return (decimal)
    analysis_years: int = 15  # Analysis horizon in years
    
    def __post_init__(self) -> None:
        """Validate economic parameters."""
        if self.e_price <= 0:
            raise ValueError(f"Strompreis muss positiv sein, war {self.e_price} €/kWh")
        if not 1 <= self.analysis_years <= 50:
            raise ValueError(f"Analysezeitraum muss zwischen 1 und 50 Jahren liegen, war {self.analysis_years}")


@dataclass
class SimulationParams:
    """Parameters for running a single simulation."""
    # Battery
    batt_loss_pct: float
    dc_coupled: bool
    min_soc_summer_pct: float
    min_soc_winter_pct: float
    max_soc_summer_pct: float
    max_soc_winter_pct: float
    
    # Inverter
    data_year: int
    inverter_limit_kw: float | None
    inverter_eff_pct: float
    
    # Consumption profile
    profile_base: list[float]
    seasonal_enabled: bool
    season_winter_pct: float
    season_summer_pct: float
    
    # Flexible load
    flex_load_enabled: bool
    flex_min_yield: float
    flex_pool_size: float
    flex_delta: list[float]
    flex_refresh_rate: float
    
    # Periodic load
    periodic_load_enabled: bool
    periodic_delta: list[float]
    periodic_interval_days: int
    
    @classmethod
    def from_config(cls, config: "SimulationConfig") -> "SimulationParams":
        """Create SimulationParams from a SimulationConfig."""
        return cls(
            batt_loss_pct=config.storage.batt_loss,
            dc_coupled=config.storage.dc_coupled,
            min_soc_summer_pct=config.storage.min_soc_summer,
            min_soc_winter_pct=config.storage.min_soc_winter,
            max_soc_summer_pct=config.storage.max_soc_summer,
            max_soc_winter_pct=config.storage.max_soc_winter,
            data_year=config.pv_system.data_year,
            inverter_limit_kw=config.inverter_limit_kw,
            inverter_eff_pct=config.pv_system.inverter_eff,
            profile_base=config.consumption.active_base,
            seasonal_enabled=config.consumption.seasonal_enabled,
            season_winter_pct=config.consumption.season_winter_pct,
            season_summer_pct=config.consumption.season_summer_pct,
            flex_load_enabled=config.consumption.flex_enabled,
            flex_min_yield=config.consumption.flex_min_yield,
            flex_pool_size=config.consumption.flex_pool,
            flex_delta=config.consumption.flex_delta,
            flex_refresh_rate=config.consumption.flex_refresh,
            periodic_load_enabled=config.consumption.periodic_enabled,
            periodic_delta=config.consumption.periodic_delta,
            periodic_interval_days=config.consumption.periodic_days,
        )


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
        return self.pv_system.feed_in_tariff / 100
    
    @property
    def total_peak_kwp(self) -> float:
        """Get total peak power of all modules."""
        return sum(m.peak for m in self.pv_system.modules)
    
    def is_valid(self) -> tuple[bool, list[str]]:
        """Check if configuration is valid for simulation."""
        missing = []
        if self.location.lat is None or self.location.lon is None:
            missing.append("📍 **Standort** – Breitengrad und Längengrad eingeben oder Ort suchen")
        if self.consumption.profile_mode == "Einfach" and self.consumption.annual_kwh is None:
            missing.append("💡 **Jahresverbrauch** – jährlichen Stromverbrauch in kWh angeben")
        return len(missing) == 0, missing
    
    def to_simulation_params(self) -> SimulationParams:
        """Create SimulationParams from this config."""
        return SimulationParams.from_config(self)


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


@dataclass(frozen=True)
class SimulationResult:
    """Result of a single simulation run."""
    grid_import: float  # Total grid import (kWh)
    total_consumption: float  # Total consumption (kWh)
    feed_in: float  # Total feed-in (kWh)
    curtailed: float  # Total curtailed energy (kWh)
    monthly: dict[int, MonthlyData]  # Monthly breakdown


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
