"""
SolarBatterYield - Main Entry Point

A Streamlit application for analyzing PV systems with battery storage.
Compares different storage configurations and investment scenarios.
"""
import numpy as np
import streamlit as st

# Configure page first (must be first Streamlit command)
st.set_page_config(page_title="SolarBatterYield", page_icon="☀️", layout="wide")

# Import application modules
from solarbatteryield.api import get_pvgis_hourly, PVGISError, APIError
from solarbatteryield.config import DEFAULTS
from solarbatteryield.models import (
    SimulationConfig, LocationConfig, ConsumptionConfig, PVSystemConfig,
    StorageConfig, EconomicsConfig, PVModule, StorageOption,
    ScenarioResult, AnalysisResult
)
from solarbatteryield.simulation import simulate
from solarbatteryield.state import init_session_state, sv
from solarbatteryield.sidebar import render_sidebar
from solarbatteryield.report import render_report, render_missing_config_message


def main():
    """Main application entry point."""
    # Initialize session state
    init_session_state()
    
    # Render sidebar configuration
    render_sidebar()
    
    # Read configuration from session state
    config = get_config()
    
    # Validate required configuration
    is_valid, missing = config.is_valid()
    if not is_valid:
        render_missing_config_message(missing)
        st.stop()
    
    # Fetch PV data and run simulation
    try:
        pv_total, pv_gen_total = fetch_pv_data(config)
    except PVGISError as exc:
        st.error(f"⚠️ {exc}")
        st.info("💡 Tipp: Überprüfe die Koordinaten und das gewählte Jahr. "
                "PVGIS unterstützt nur bestimmte Jahre und Regionen.")
        st.stop()
    except APIError as exc:
        st.error(f"⚠️ {exc}")
        st.info("💡 Bitte versuche es später erneut oder prüfe deine Internetverbindung.")
        st.stop()
    except ValueError as exc:
        st.error(f"⚠️ Konfigurationsfehler: {exc}")
        st.stop()
    
    # Run simulations for all scenarios
    results = run_simulations(config, pv_total, pv_gen_total)
    
    # Render report
    render_report(config, results)


def get_config() -> SimulationConfig:
    """Read all configuration values from session state and return SimulationConfig."""
    inverter_limit_enabled = sv("cfg_inverter_limit_enabled")
    flex_enabled = sv("cfg_flex_enabled")
    periodic_enabled = sv("cfg_periodic_enabled")
    
    # Build PV modules list
    modules = [
        PVModule(
            id=m["id"],
            name=m["name"],
            peak=m["peak"],
            azi=m["azi"],
            slope=m["slope"]
        )
        for m in st.session_state.modules
    ]
    
    # Build storage options list
    storage_options = [
        StorageOption(
            id=s["id"],
            name=s["name"],
            cap=s["cap"],
            cost=s["cost"]
        )
        for s in st.session_state.storages
    ]
    
    # Get day-type profiles if enabled
    use_day_types = st.session_state.get("cfg_use_day_types", False)
    profile_saturday = None
    profile_sunday = None
    if use_day_types and sv("cfg_profile_mode") == "Erweitert":
        profile_saturday = st.session_state.get("_profile_saturday")
        profile_sunday = st.session_state.get("_profile_sunday")
    
    # Get yearly profile for expert mode
    yearly_profile = None
    if sv("cfg_profile_mode") == "Experte":
        yearly_profile = st.session_state.get("_yearly_profile")
    
    return SimulationConfig(
        location=LocationConfig(
            lat=sv("cfg_lat"),
            lon=sv("cfg_lon"),
        ),
        consumption=ConsumptionConfig(
            profile_mode=sv("cfg_profile_mode"),
            annual_kwh=sv("cfg_annual_kwh"),
            active_base=st.session_state._active_base,
            profile_saturday=profile_saturday,
            profile_sunday=profile_sunday,
            yearly_profile=yearly_profile,
            seasonal_enabled=sv("cfg_seasonal_enabled"),
            season_winter_pct=sv("cfg_season_winter"),
            season_summer_pct=sv("cfg_season_summer"),
            flex_enabled=flex_enabled,
            flex_delta=st.session_state._flex_delta if flex_enabled else [0] * 24,
            flex_min_yield=sv("cfg_flex_min_yield"),
            flex_pool=sv("cfg_flex_pool"),
            flex_refresh=sv("cfg_flex_refresh"),
            periodic_enabled=periodic_enabled,
            periodic_delta=st.session_state._periodic_delta if periodic_enabled else [0] * 24,
            periodic_days=sv("cfg_periodic_days"),
        ),
        pv_system=PVSystemConfig(
            data_year=sv("cfg_year"),
            system_loss=sv("cfg_loss"),
            inverter_efficiency_preset=sv("cfg_inverter_efficiency_preset"),
            inverter_efficiency_custom=st.session_state.get("_inverter_eff_custom", []),
            inverter_limit_enabled=inverter_limit_enabled,
            inverter_limit_w=sv("cfg_inverter_limit_w"),
            base_cost=sv("cfg_base_cost"),
            modules=modules,
        ),
        storage=StorageConfig(
            dc_coupled=sv("cfg_dc_coupled") == "DC-gekoppelt",
            batt_loss=sv("cfg_batt_loss"),
            batt_inverter_preset=sv("cfg_batt_inverter_preset"),
            batt_inverter_efficiency_custom=st.session_state.get("_batt_inverter_eff_custom", []),
            min_soc_summer=sv("cfg_min_soc_s"),
            max_soc_summer=sv("cfg_max_soc_s"),
            min_soc_winter=sv("cfg_min_soc_w"),
            max_soc_winter=sv("cfg_max_soc_w"),
            options=storage_options,
        ),
        economics=EconomicsConfig(
            e_price=sv("cfg_e_price") / 100,  # Convert ct/kWh to EUR/kWh
            e_inc=sv("cfg_e_inc") / 100,
            feed_in_tariff=sv("cfg_feed_in_tariff"),
            etf_ret=sv("cfg_etf_ret") / 100,
            analysis_years=sv("cfg_years"),
        ),
    )


def fetch_pv_data(config: SimulationConfig) -> tuple[np.ndarray, float]:
    """Fetch PV generation data from PVGIS for all modules."""
    with st.spinner("Lade PV-Ertragsdaten von PVGIS …"):
        pv_arrays = []
        for mod in config.pv_system.modules:
            arr = get_pvgis_hourly(
                config.lat, config.lon, mod.peak, mod.slope, mod.azi,
                config.pv_system.system_loss, config.pv_system.data_year,
            )
            pv_arrays.append(arr)
        pv_total = sum(pv_arrays)
        pv_gen_total = float(np.sum(pv_total))
    return pv_total, pv_gen_total


def run_simulations(config: SimulationConfig, pv_total: np.ndarray, 
                    pv_gen_total: float) -> AnalysisResult:
    """Run simulations for all storage scenarios."""
    # Build scenario list: base (no storage) + each storage option sorted by capacity
    sorted_storages = sorted(config.storage.options, key=lambda s: s.cap)
    scenarios = [("Ohne Speicher", 0.0, config.pv_system.base_cost)]
    for s in sorted_storages:
        scenarios.append((
            f"{s.name} ({s.cap:.2f} kWh)",
            s.cap,
            config.pv_system.base_cost + s.cost
        ))

    # Get simulation parameters from config
    sim_params = config.to_simulation_params()

    results = AnalysisResult(pv_generation_total=pv_gen_total)
    
    for name, cap, cost in scenarios:
        sim_result = simulate(pv_total, cap, sim_params)
        
        results.scenarios.append(ScenarioResult(
            name=name,
            storage_capacity=cap,
            investment_cost=cost,
            simulation=sim_result,
        ))

    return results


if __name__ == "__main__":
    main()

