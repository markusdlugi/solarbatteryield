"""
Prices and comparison section of the sidebar.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.config import LIMITS
from solarbatteryield.state import widget_value


def render_prices_section() -> None:
    """
    Render the prices and comparison section.
    
    Provides settings for:
    - Electricity price and annual increase
    - Feed-in tariff
    - ETF return rate
    - Savings reinvestment option
    - Analysis horizon
    """
    with st.sidebar.expander("💰 Preise & Vergleich"):
        st.number_input(
            "Strompreis (ct/kWh)", step=1.0, format="%.2f", key="cfg_e_price",
            min_value=LIMITS.e_price_min, max_value=LIMITS.e_price_max,
            **widget_value("cfg_e_price")
        )
        st.number_input(
            "Strompreis-Steigerung (%/a)", step=0.5, format="%.1f", key="cfg_e_inc",
            min_value=LIMITS.e_inc_min, max_value=LIMITS.e_inc_max,
            **widget_value("cfg_e_inc")
        )
        st.number_input(
            "Einspeisevergütung (ct/kWh)", step=0.5, min_value=0.0,
            format="%.1f", key="cfg_feed_in_tariff",
            help="Vergütung für ins Netz eingespeisten Strom. "
                 "In Deutschland aktuell ca. 8,0 ct/kWh für Anlagen bis 10 kWp. "
                 "Bei Balkonkraftwerken in der Regel keine Vergütung aufgrund vereinfachter Anmeldung.",
            **widget_value("cfg_feed_in_tariff")
        )
        st.number_input(
            "ETF-Rendite (%/a)", step=0.5, format="%.1f", key="cfg_etf_ret",
            help="Angenommene Rendite eines beispielhaften ETF als alternatives Investment.",
            min_value=LIMITS.etf_ret_min, max_value=LIMITS.etf_ret_max,
            **widget_value("cfg_etf_ret")
        )
        st.toggle(
            "💸 Ersparnisse reinvestieren", key="cfg_reinvest_savings",
            help="Die monatlichen Ersparnisse aus der PV-Nutzung werden reinvestiert "
                 "und mit der ETF-Rendite verzinst. Die angezeigten Ergebnisse sind "
                 "nur zu erreichen, wenn jegliche Ersparnisse konsequent per Sparplan "
                 "investiert werden.",
            **widget_value("cfg_reinvest_savings")
        )
        st.slider(
            "Analyse-Horizont (Jahre)", LIMITS.years_min, LIMITS.years_max,
            key="cfg_years",
            **widget_value("cfg_years")
        )

