"""
Report footer components: share button and data attribution.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.state import create_share_url


def render_share_button() -> None:
    """
    Render the configuration sharing button.
    
    Creates a shareable URL with all current configuration parameters.
    Attempts to create a short URL using DynamoDB persistence, falls back
    to a long URL with embedded config if unavailable.
    """
    st.divider()
    if st.button("🔗 Link mit aktueller Konfiguration erstellen"):
        try:
            base_url = st.context.headers.get("Origin", "")
            share_url, is_short = create_share_url(base_url)
            st.code(share_url, language=None)
            if is_short:
                st.caption("Link kopieren und teilen – Konfiguration wurde gespeichert.")
            else:
                st.caption("Link kopieren und teilen – alle Parameter sind im Link gespeichert.")
            st.caption("🔒 Der Standort wird beim Teilen auf ~2 km gerundet, um deine Privatsphäre zu schützen.")
        except Exception as exc:
            st.error(f"Fehler beim Erstellen des Links: {exc}")

    render_data_attribution()


def render_data_attribution() -> None:
    """
    Render data source attribution footer.
    
    Credits PVGIS and OpenStreetMap as data sources.
    """
    st.divider()
    st.caption(
        "📊 Datenquellen: PV-Daten © [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/) (European Commission) · "
        "Geocoding © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, "
        "[ODbL](https://opendatacommons.org/licenses/odbl/)"
    )

