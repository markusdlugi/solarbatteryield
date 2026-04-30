"""
Landing page component.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.report.footer import render_data_attribution


def render_landing_page(missing: list[str]) -> None:
    """
    Render the application landing page.

    Displays a welcome message, lists any missing configuration parameters,
    and describes the default system that will be used once configured.

    Args:
        missing: List of missing configuration items with descriptions
    """
    st.title("☀️ SolarBatterYield - PV-Rechner mit Speichervergleich")
    st.markdown(
        "Open-Source-Simulation von PV-Ertrag und Amortisation für Balkonkraftwerke. "
        "Berechne die ideale Speicher-Nachrüstung und optimiere deinen Eigenverbrauch."
    )
    missing_list = "\n".join(f"- {m}" for m in missing)
    st.info(
        "Bitte konfiguriere mindestens folgende Parameter in der "
        "**Seitenleiste** (» oben links), "
        f"um die Analyse zu starten:\n\n{missing_list}"
    )

    st.markdown(
        "Nach Hinzufügen der erforderlichen Parameter wird ein Report mit Standardwerten generiert. "
        "Er verwendet ein beispielhaftes System, bestehend aus:"
    )
    st.markdown("- ☀️ PV-Modulen mit 2kWp Leistung in Südausrichtung")
    st.markdown("- 🔋️ drei unterschiedlichen Speicherkonfigurationen mit bis zu 6kWh")
    st.markdown(
        "Du kannst diese beliebig erweitern, ändern, löschen oder zusätzliche Einstellungen anpassen - "
        "der Report wird automatisch aktualisiert."
    )

    render_data_attribution()
