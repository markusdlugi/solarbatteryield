"""
Report header section with key metrics.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.report.context import ReportContext, get_short_place_name
from solarbatteryield.utils import de


def render_header(ctx: ReportContext) -> None:
    """
    Render the main header section with key metrics.
    
    Displays:
    - Title with location info
    - Key metrics: consumption, cost, PV power, PV generation
    
    Args:
        ctx: Report context with config and results
    """
    st.title("☀️ SolarBatterYield - PV-Rechner mit Speichervergleich")

    place_name = get_short_place_name()
    if place_name:
        location_str = f"{place_name} ({ctx.lat}°N / {ctx.lon}°E)"
    else:
        location_str = f"{ctx.lat}°N / {ctx.lon}°E"

    st.caption(f"PVGIS-Stundenwerte {ctx.data_year}  ·  Standort {location_str}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Gesamtverbrauch", f"{de(ctx.total_consumption)} kWh/a")
    col2.metric("Stromkosten ohne PV", f"{de(ctx.total_consumption * ctx.e_price)} €/a")
    col3.metric("PV-Leistung", f"{de(ctx.total_peak_kwp, 1)} kWp")
    col4.metric("PV-Erzeugung", f"{de(ctx.pv_generation_total)} kWh/a")
