"""
Report context providing shared data for all report components.

The ReportContext encapsulates all configuration and results needed by report
components, avoiding the need to pass many parameters to each component.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from solarbatteryield.models import SimulationConfig, AnalysisResult, ScenarioResult


def get_short_place_name() -> str | None:
    """
    Get a short, readable place name from session state.

    The location name is stored in session state by the sidebar,
    either from geocoding (forward lookup) or reverse geocoding.

    Returns:
        Short place name like "München, Bayern" or None if not available.
    """
    return st.session_state.get("_location_display_name")


@dataclass
class ReportContext:
    """
    Shared context for all report components.
    
    Encapsulates configuration and results, providing convenient accessors
    for commonly used values.
    """
    config: SimulationConfig
    results: AnalysisResult

    # ─── Convenience properties ─────────────────────────────────────────────────

    @property
    def e_price(self) -> float:
        """Electricity price in EUR/kWh."""
        return self.config.economics.e_price

    @property
    def e_inc(self) -> float:
        """Annual electricity price increase (decimal)."""
        return self.config.economics.e_inc

    @property
    def etf_ret(self) -> float:
        """Annual ETF return (decimal)."""
        return self.config.economics.etf_ret

    @property
    def feed_in_tariff(self) -> float:
        """Feed-in tariff in EUR/kWh."""
        return self.config.feed_in_tariff_eur

    @property
    def analysis_years(self) -> int:
        """Analysis horizon in years."""
        return self.config.economics.analysis_years

    @property
    def reinvest_savings(self) -> bool:
        """Whether to reinvest savings with ETF return."""
        return self.config.economics.reinvest_savings

    @property
    def total_consumption(self) -> float:
        """Total annual consumption in kWh."""
        return self.results.total_consumption

    @property
    def scenarios(self) -> list[ScenarioResult]:
        """List of scenario results."""
        return self.results.scenarios

    @property
    def pv_generation_total(self) -> float:
        """Total PV generation in kWh/year."""
        return self.results.pv_generation_total

    @property
    def lat(self) -> float | None:
        """Latitude of location."""
        return self.config.lat

    @property
    def lon(self) -> float | None:
        """Longitude of location."""
        return self.config.lon

    @property
    def data_year(self) -> int:
        """PVGIS data year."""
        return self.config.pv_system.data_year

    @property
    def total_peak_kwp(self) -> float:
        """Total PV peak power in kWp."""
        return self.config.total_peak_kwp

    @property
    def min_load_w(self) -> float:
        """Effective base-load floor used in simulation (W)."""
        return self.results.min_load_w

    @property
    def min_load_w_is_override(self) -> bool:
        """Whether the base-load floor is a manual override."""
        return self.config.consumption.min_load_w_override is not None
