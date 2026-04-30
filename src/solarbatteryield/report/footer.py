"""
Report footer components: share button, data attribution, and sidebar CTA.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.state import create_share_url, show_shared_url_hint


def render_share_button() -> None:
    """
    Render the configuration sharing section.

    If the report was opened via a shared link and the user has not yet
    modified the configuration, a CTA prompting sidebar usage is shown
    instead of the (redundant) share button.  Once the user modifies
    something, the normal share button appears.
    """
    st.divider()

    if show_shared_url_hint():
        # Replace share button with CTA – creating a new link would be
        # identical to the one already used, so offer guidance instead.
        st.info(
            "💡 **Du möchtest deinen eigenen Report erstellen?** "
            "Passe einfach die Konfiguration in der "
            "**Seitenleiste** (» oben links) an – "
            "der Report wird automatisch aktualisiert.",
            icon="🛠️",
        )
    else:
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

