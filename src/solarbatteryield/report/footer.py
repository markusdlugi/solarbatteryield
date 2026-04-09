"""
Report footer components: share button and data attribution.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.state import encode_config


def render_share_button() -> None:
    """
    Render the configuration sharing button.
    
    Creates a shareable URL with all current configuration parameters
    encoded as a compressed base64 string.
    """
    st.divider()
    if st.button("🔗 Link mit aktueller Konfiguration erstellen"):
        try:
            encoded = encode_config()
            base_url = st.context.headers.get("Origin", "")
            share_url = f"{base_url}/?cfg={encoded}"
            st.code(share_url, language=None)
            st.caption("Link kopieren und teilen – alle Parameter sind im Link gespeichert.")
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

