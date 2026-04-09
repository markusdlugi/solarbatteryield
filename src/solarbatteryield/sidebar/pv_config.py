"""
PV modules and system configuration sections of the sidebar.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from solarbatteryield.config import LIMITS
from solarbatteryield.simulation.inverter_efficiency import (
    DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT,
    INVERTER_EFFICIENCY_CURVES,
)
from solarbatteryield.state import sv, widget_value, selectbox_index


def render_pv_modules_section() -> None:
    """
    Render the PV modules configuration section.
    
    Allows adding, editing, and removing PV modules with
    individual power, azimuth, and slope settings.
    """
    with st.sidebar.expander("☀️ PV-Module"):
        modules = st.session_state.modules
        for i, mod in enumerate(modules):
            mid = mod["id"]
            with st.expander(f"**{mod['name']}** – {mod['peak']} kWp"):
                modules[i]["name"] = st.text_input("Name", value=mod["name"], key=f"mn_{mid}")
                modules[i]["peak"] = st.number_input(
                    "Leistung (kWp)", value=mod["peak"], step=0.1, min_value=0.1,
                    format="%.2f", key=f"mp_{mid}",
                )
                modules[i]["azi"] = st.number_input(
                    "Azimut (°)", value=mod["azi"], step=5,
                    help="0 = Süd, 90 = West, -90 = Ost", key=f"ma_{mid}",
                )
                modules[i]["slope"] = st.slider(
                    "Neigung (°)", 0, 90, mod["slope"], key=f"ms_{mid}",
                    help="0° = horizontal (flach), 90° = vertikal (senkrecht an der Wand)",
                )
                if len(modules) > 1 and st.button("🗑️ Modul entfernen", key=f"md_{mid}"):
                    modules.pop(i)
                    st.rerun()
        if st.button("➕ Modul hinzufügen"):
            modules.append({
                "id": st.session_state.next_mod_id,
                "name": f"Modul {len(modules) + 1}",
                "peak": 0.5, "azi": 0, "slope": 30,
            })
            st.session_state.next_mod_id += 1
            st.rerun()
        st.divider()
        st.number_input("Kosten PV-System ohne Speicher (€)", step=50, key="cfg_base_cost",
                        **widget_value("cfg_base_cost"))


def render_pv_config_section() -> None:
    """
    Render the PV system configuration section.
    
    Provides settings for:
    - PVGIS data year
    - System losses
    - Inverter efficiency curve
    - Inverter limit
    """
    with st.sidebar.expander("⚡ PV-Konfiguration"):
        _year_options = list(range(LIMITS.year_min, LIMITS.year_max + 1))
        st.selectbox(
            "PVGIS-Datenjahr", _year_options,
            key="cfg_year",
            help="Das Jahr für die Analyse. 2015 war ein gutes Durchschnittsjahr.",
            **selectbox_index("cfg_year", _year_options)
        )
        st.slider(
            "PV System-Verluste (%)", LIMITS.loss_min, LIMITS.loss_max, key="cfg_loss",
            help="Verluste durch Kabel, Verschmutzung, Temperatur, Mismatch etc. "
                 "**Ohne Wechselrichterverluste**, da diese separat berechnet werden (s.u.), "
                 "daher etwas niedriger als PVGIS-Empfehlung von 14%.",
            **widget_value("cfg_loss")
        )

        # Inverter efficiency curve selection
        _render_inverter_efficiency_section()

        st.toggle(
            "⚡ Wechselrichter-Limit", key="cfg_inverter_limit_enabled",
            **widget_value("cfg_inverter_limit_enabled")
        )
        if sv("cfg_inverter_limit_enabled"):
            st.number_input(
                "Wechselrichter-Limit (W)", step=100,
                min_value=LIMITS.inverter_limit_w_min,
                key="cfg_inverter_limit_w",
                help="Maximale AC-Ausgangsleistung des Wechselrichters in Watt.",
                **widget_value("cfg_inverter_limit_w")
            )


def _render_inverter_efficiency_section() -> None:
    """Render inverter efficiency curve selection and custom curve editor."""
    _preset_options = {
        "pessimistic": "🔻 Pessimistisch (P10)",
        "median": "📊 Durchschnittlich (P50)",
        "optimistic": "🔺 Optimistisch (P90)",
        "custom": "⚙️ Benutzerdefiniert",
    }

    _preset_keys = list(_preset_options.keys())

    st.selectbox(
        "📈 WR-Wirkungsgradkurve",
        options=_preset_keys,
        format_func=lambda x: _preset_options[x],
        key="cfg_inverter_efficiency_preset",
        help="Wirkungsgrad des Wechselrichters variiert mit der Leistung. "
             "Basierend auf CEC-Daten (California Energy Commission) von ~3.000 Wechselrichtern. "
             "P10 = 10. Perzentil (konservativ), P50 = Median (typisch), P90 = 90. Perzentil (Premium-Geräte).",
        **selectbox_index("cfg_inverter_efficiency_preset", _preset_keys),
    )

    if sv("cfg_inverter_efficiency_preset") == "custom":
        _render_custom_efficiency_editor()
    else:
        _show_efficiency_curve_info(sv("cfg_inverter_efficiency_preset"))


def _render_custom_efficiency_editor() -> None:
    """Render the custom efficiency curve editor."""
    if "_inverter_eff_custom" not in st.session_state:
        st.session_state._inverter_eff_custom = list(DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT)

    st.caption("Wirkungsgrad (%) bei verschiedenen Leistungsstufen")

    power_levels = [10, 20, 30, 50, 75, 100]

    eff_df = pd.DataFrame({
        "Leistung (%)": [f"{p}%" for p in power_levels],
        "Wirkungsgrad (%)": st.session_state._inverter_eff_custom,
    })

    edited_eff = st.data_editor(
        eff_df,
        disabled=["Leistung (%)"],
        hide_index=True,
        width="stretch",
        key="inverter_eff_editor",
        column_config={
            "Wirkungsgrad (%)": st.column_config.NumberColumn(
                min_value=70.0,
                max_value=100.0,
                step=0.1,
                format="%.2f",
            ),
        },
    )

    new_values = edited_eff["Wirkungsgrad (%)"].tolist()
    if new_values != st.session_state._inverter_eff_custom:
        st.session_state._inverter_eff_custom = new_values
        st.rerun()

    st.caption(
        "💡 Tipp: CEC-Wechselrichterdaten unter "
        "[energy.ca.gov](https://www.energy.ca.gov/programs-and-topics/programs/solar-equipment-lists) prüfen"
    )


def _show_efficiency_curve_info(preset: str) -> None:
    """Show information about the selected efficiency curve preset."""
    if preset not in INVERTER_EFFICIENCY_CURVES:
        return

    curve = INVERTER_EFFICIENCY_CURVES[preset]

    # Show a compact summary
    eff_10 = curve[0][1] * 100
    eff_50 = curve[3][1] * 100  # 50% power level
    eff_100 = curve[5][1] * 100

    st.caption(f"η: {eff_10:.1f}% (10%) → {eff_50:.1f}% (50%) → {eff_100:.1f}% (100%)")

