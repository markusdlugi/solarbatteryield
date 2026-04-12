"""
Storage options and configuration sections of the sidebar.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from solarbatteryield.config import LIMITS
from solarbatteryield.simulation.inverter_efficiency import (
    DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT,
    INVERTER_EFFICIENCY_CURVES,
)
from solarbatteryield.state import sv, widget_value, selectbox_index, radio_index


def render_storage_options_section() -> None:
    """Render the storage options section with add/edit/remove functionality."""
    with st.sidebar.expander("🔋 Speicher-Optionen"):
        storages = st.session_state.storages
        for i, stor in enumerate(storages):
            sid = stor["id"]
            with st.expander(f"**{stor['name']}** – {stor['cap']} kWh"):
                storages[i]["name"] = st.text_input("Name", value=stor["name"], key=f"sn_{sid}")
                storages[i]["cap"] = st.number_input(
                    "Kapazität (kWh)", value=stor["cap"], step=0.1, min_value=0.1,
                    format="%.2f", key=f"sc_{sid}",
                )
                storages[i]["cost"] = st.number_input(
                    "Aufpreis ggü. Basis-System (€)", value=stor["cost"], step=50,
                    min_value=0, key=f"sp_{sid}",
                )
                if st.button("🗑️ Speicher-Option entfernen", key=f"sd_{sid}"):
                    storages.pop(i)
                    st.rerun()
        if st.button("➕ Speicher-Option hinzufügen"):
            storages.append({
                "id": st.session_state.next_stor_id,
                "name": f"Speicher {len(storages) + 1}",
                "cap": 2.0, "cost": 500,
            })
            st.session_state.next_stor_id += 1
            st.rerun()


def render_storage_config_section() -> None:
    """Render the storage configuration section."""
    with st.sidebar.expander("🪫 Speicher-Konfiguration"):
        _coupling_options = ["DC-gekoppelt", "AC-gekoppelt"]
        st.radio(
            "Speicheranbindung", _coupling_options, horizontal=True,
            key="cfg_dc_coupled",
            help="**DC-gekoppelt**: Batterie lädt ohne Limit direkt von den Panels. "
                 "**AC-gekoppelt**: Batterie lädt von AC über eigenen Batterie-WR.",
            **radio_index("cfg_dc_coupled", _coupling_options),
        )

        if sv("cfg_dc_coupled") == "AC-gekoppelt":
            _render_batt_inverter_efficiency_section()

        _render_discharge_strategy_section()

        st.slider(
            "Zellverluste Laden/Entladen (%)", LIMITS.batt_loss_min, LIMITS.batt_loss_max,
            key="cfg_batt_loss",
            help="Verluste in den Batteriezellen beim Laden und Entladen.",
            **widget_value("cfg_batt_loss")
        )

        _render_soc_sliders()


def _render_batt_inverter_efficiency_section() -> None:
    """Render battery inverter efficiency curve selection."""
    _preset_options = {
        "pessimistic": "🔻 Pessimistisch (P10)",
        "median": "📊 Durchschnittlich (P50)",
        "optimistic": "🔺 Optimistisch (P90)",
        "custom": "⚙️ Benutzerdefiniert",
    }
    _preset_keys = list(_preset_options.keys())

    st.selectbox(
        "📈 Batterie-WR-Wirkungsgradkurve",
        options=_preset_keys,
        format_func=lambda x: _preset_options[x],
        key="cfg_batt_inverter_preset",
        help="Wirkungsgrad des bidirektionalen Batterie-Wechselrichters (AC↔DC).",
        **selectbox_index("cfg_batt_inverter_preset", _preset_keys),
    )

    if sv("cfg_batt_inverter_preset") == "custom":
        _render_batt_inverter_custom_editor()
    else:
        _show_efficiency_curve_info(sv("cfg_batt_inverter_preset"))


def _render_batt_inverter_custom_editor() -> None:
    """Render the custom battery inverter efficiency curve editor."""
    if "_batt_inverter_eff_custom" not in st.session_state:
        st.session_state._batt_inverter_eff_custom = list(DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT)

    st.caption("Batterie-WR-Wirkungsgrad (%) bei verschiedenen Leistungsstufen")
    power_levels = [10, 20, 30, 50, 75, 100]

    eff_df = pd.DataFrame({
        "Leistung (%)": [f"{p}%" for p in power_levels],
        "Wirkungsgrad (%)": st.session_state._batt_inverter_eff_custom,
    })

    edited_eff = st.data_editor(
        eff_df, disabled=["Leistung (%)"], hide_index=True, width="stretch",
        key="batt_inverter_eff_editor",
        column_config={
            "Wirkungsgrad (%)": st.column_config.NumberColumn(
                min_value=70.0, max_value=100.0, step=0.1, format="%.2f",
            ),
        },
    )

    new_values = edited_eff["Wirkungsgrad (%)"].tolist()
    if new_values != st.session_state._batt_inverter_eff_custom:
        st.session_state._batt_inverter_eff_custom = new_values
        st.rerun()


def _show_efficiency_curve_info(preset: str) -> None:
    """Show efficiency curve summary."""
    if preset not in INVERTER_EFFICIENCY_CURVES:
        return
    curve = INVERTER_EFFICIENCY_CURVES[preset]
    eff_10, eff_50, eff_100 = curve[0][1] * 100, curve[3][1] * 100, curve[5][1] * 100
    st.caption(f"η: {eff_10:.1f}% (10%) → {eff_50:.1f}% (50%) → {eff_100:.1f}% (100%)")


def _render_discharge_strategy_section() -> None:
    """Render discharge strategy selection and related inputs."""
    _strategy_options = {
        "zero_feed_in": "🎯 Nulleinspeisung",
        "base_load": "⚡ Grundlastdeckung",
        "time_window": "🕐 Zeitfenster",
    }
    _strategy_keys = list(_strategy_options.keys())

    st.selectbox(
        "Entladestrategie",
        options=_strategy_keys,
        format_func=lambda x: _strategy_options[x],
        key="cfg_discharge_strategy",
        help="**Nulleinspeisung**: Batterie passt Leistung kontinuierlich an Hausverbrauch an **(erfordert Smart Meter)**. "
             "**Grundlastdeckung**: Konstante Einspeisung. "
             "**Zeitfenster**: Entladung nur in konfigurierten Zeitfenstern.",
        **selectbox_index("cfg_discharge_strategy", _strategy_keys),
    )

    strategy = sv("cfg_discharge_strategy")

    if strategy == "base_load":
        st.number_input(
            "Leistung (W)", min_value=50, max_value=10000, step=50,
            key="cfg_discharge_base_load_w",
            help="Konstante AC-Ausgangsleistung des Systems (PV + Batterie). "
                 "Nur wenn die Batterie voll ist, wird die Leistung überschritten und die gesamte PV-Leistung eingespeist.",
            **widget_value("cfg_discharge_base_load_w"),
        )

    if strategy == "time_window":
        _render_time_windows_editor()


def _render_time_windows_editor() -> None:
    """Render dynamic time window editor for time_window strategy using data_editor."""
    # Default time windows optimized for typical H0 load profile
    # Full day coverage with power levels matching consumption patterns
    _default_windows = [
        {"start": 0, "end": 6, "power_w": 150},  # Nacht (Standby)
        {"start": 6, "end": 9, "power_w": 300},  # Morgens (Frühstück)
        {"start": 9, "end": 17, "power_w": 200},  # Tagsüber (PV-Stunden)
        {"start": 17, "end": 0, "power_w": 350},  # Abends (Hauptverbrauch)
    ]

    if "_discharge_time_windows" not in st.session_state:
        st.session_state._discharge_time_windows = _default_windows.copy()

    windows = st.session_state._discharge_time_windows

    # Create formatted hour options
    hour_options = [f"{h:02d}:00" for h in range(24)]

    # Create DataFrame with formatted time strings
    if windows:
        df = pd.DataFrame({
            "start": [f"{w['start']:02d}:00" for w in windows],
            "end": [f"{w['end']:02d}:00" for w in windows],
            "power_w": [w["power_w"] for w in windows],
        })
    else:
        df = pd.DataFrame(columns=["start", "end", "power_w"])

    # Configure the data editor with proper column types
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key="tw_data_editor",
        column_config={
            "start": st.column_config.SelectboxColumn(
                "Von",
                options=hour_options,
                help="Startzeit des Zeitfensters",
                required=True,
            ),
            "end": st.column_config.SelectboxColumn(
                "Bis",
                options=hour_options,
                help="Endzeit des Zeitfensters",
                required=True,
            ),
            "power_w": st.column_config.NumberColumn(
                "Leistung (W)",
                min_value=50,
                max_value=10000,
                step=50,
                default=200,
                help="Entladeleistung in Watt",
                required=True,
            ),
        },
    )

    # Convert edited DataFrame back to list of dicts with integer hours
    new_windows = []
    for _, row in edited_df.iterrows():
        start_str = row.get("start")
        end_str = row.get("end")
        power = row.get("power_w")

        # Parse HH:00 format back to integer, with defaults for new/empty rows
        start = int(start_str.split(":")[0]) if pd.notna(start_str) and start_str else 17
        end = int(end_str.split(":")[0]) if pd.notna(end_str) and end_str else 22
        power_w = int(power) if pd.notna(power) else 200

        new_windows.append({"start": start, "end": end, "power_w": power_w})

    if new_windows != windows:
        st.session_state._discharge_time_windows = new_windows


def _render_soc_sliders() -> None:
    """Render SoC limit sliders with auto-correction for invalid values."""

    def _on_min_soc_s_change():
        st.session_state._last_soc_change = "min_s"

    def _on_max_soc_s_change():
        st.session_state._last_soc_change = "max_s"

    def _on_min_soc_w_change():
        st.session_state._last_soc_change = "min_w"

    def _on_max_soc_w_change():
        st.session_state._last_soc_change = "max_w"

    _last_change = st.session_state.get("_last_soc_change")

    # Fix invalid summer SoC
    _min_s, _max_s = sv("cfg_min_soc_s"), sv("cfg_max_soc_s")
    if _min_s > _max_s:
        if _last_change == "min_s":
            st.session_state.cfg_min_soc_s = _max_s
        else:
            st.session_state.cfg_max_soc_s = _min_s
        st.session_state._last_soc_change = None

    # Fix invalid winter SoC
    _min_w, _max_w = sv("cfg_min_soc_w"), sv("cfg_max_soc_w")
    if _min_w > _max_w:
        if _last_change == "min_w":
            st.session_state.cfg_min_soc_w = _max_w
        else:
            st.session_state.cfg_max_soc_w = _min_w
        st.session_state._last_soc_change = None

    st.slider("☀️ Min. Ladezustand Sommer (%)", LIMITS.soc_min, LIMITS.soc_max,
              key="cfg_min_soc_s", on_change=_on_min_soc_s_change,
              help="Kann nicht höher als Max. Ladezustand sein.",
              **widget_value("cfg_min_soc_s"))
    st.slider("☀️ Max. Ladezustand Sommer (%)", LIMITS.soc_min, LIMITS.soc_max,
              key="cfg_max_soc_s", on_change=_on_max_soc_s_change,
              help="Kann nicht niedriger als Min. Ladezustand sein.",
              **widget_value("cfg_max_soc_s"))
    st.slider("❄️ Min. Ladezustand Winter (%)", LIMITS.soc_min, LIMITS.soc_max,
              key="cfg_min_soc_w", on_change=_on_min_soc_w_change,
              help="Kann nicht höher als Max. Ladezustand sein.",
              **widget_value("cfg_min_soc_w"))
    st.slider("❄️ Max. Ladezustand Winter (%)", LIMITS.soc_min, LIMITS.soc_max,
              key="cfg_max_soc_w", on_change=_on_max_soc_w_change,
              help="Kann nicht niedriger als Min. Ladezustand sein.",
              **widget_value("cfg_max_soc_w"))
