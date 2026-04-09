"""
Consumption configuration section of the sidebar.

Handles simple (H0), advanced, and expert consumption profile modes.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from solarbatteryield.config import PROFILE_SATURDAY, PROFILE_SUNDAY, LIMITS, scale_profiles
from solarbatteryield.state import sv, widget_value, radio_index
from solarbatteryield.sidebar.profile_io import (
    generate_yearly_template_csv,
    parse_yearly_profile_csv,
    get_hours_in_year,
    calculate_profile_stats,
)


def render_consumption_section() -> None:
    """
    Render the consumption configuration section.
    
    Provides three modes:
    - Einfach: H0 standard profile with annual consumption
    - Erweitert: Custom hourly profiles with optional seasonal scaling
    - Experte: Full year CSV upload
    """
    with st.sidebar.expander("💡 Verbrauch", expanded=True):
        _profile_modes = ["Einfach", "Erweitert", "Experte"]
        st.radio(
            "Lastprofil-Modus", _profile_modes, horizontal=True,
            key="cfg_profile_mode",
            help="**Einfach**: BDEW H0-Standardlastprofil mit Unterscheidung nach Wochentag/Samstag/Sonntag. "
                 "**Erweitert**: Eigenes stündliches Lastprofil mit optionaler Saisonskalierung. "
                 "**Experte**: Eigene Jahresdaten aus Smart-Meter als CSV hochladen.",
            **radio_index("cfg_profile_mode", _profile_modes),
        )

        # Detect switch from Einfach → Erweitert: pre-fill profiles from annual kWh
        current_mode = sv("cfg_profile_mode")
        if current_mode == "Erweitert" and st.session_state.get("_prev_profile_mode") == "Einfach":
            annual = sv("cfg_annual_kwh") or 3000.0
            base, sat, sun = scale_profiles(annual)
            st.session_state._active_base = base
            st.session_state._profile_saturday = sat
            st.session_state._profile_sunday = sun
        st.session_state._prev_profile_mode = current_mode

        if current_mode == "Einfach":
            _render_simple_mode()
        elif current_mode == "Erweitert":
            _render_advanced_mode()
        else:  # Experte
            _render_expert_mode()


def _render_simple_mode() -> None:
    """Render simple mode with H0 profile."""
    st.number_input(
        "Jahresverbrauch (kWh)", step=100,
        min_value=LIMITS.annual_kwh_min, key="cfg_annual_kwh",
        placeholder="z. B. 3000",
        **widget_value("cfg_annual_kwh"),
    )
    st.caption(
        "📊 Das BDEW H0-Standardlastprofil berücksichtigt automatisch "
        "unterschiedliche Verbräuche an Werktagen, Samstagen und Sonn-/Feiertagen "
        "sowie saisonale Unterschiede."
    )
    _render_flex_load_settings()
    _render_periodic_load_settings()


def _render_advanced_mode() -> None:
    """Render advanced mode with custom profiles."""
    _render_advanced_profile_settings()
    _render_seasonal_settings()
    _render_flex_load_settings()
    _render_periodic_load_settings()


def _render_expert_mode() -> None:
    """Render expert mode with CSV upload."""
    _render_expert_profile_settings()


def _render_advanced_profile_settings() -> None:
    """Render advanced profile settings with optional day-type differentiation."""
    st.caption("Verbrauch in Watt für jede Stunde eines typischen Tages")

    # Check if day-type profiles are enabled
    use_day_types = st.toggle(
        "📅 Wochentag-Unterscheidung",
        key="cfg_use_day_types",
        help="Separate Profile für Werktage, Samstage und Sonn-/Feiertage",
        **widget_value("cfg_use_day_types", False),
    )

    if use_day_types:
        _render_day_type_profiles()
    else:
        _render_single_profile()


def _render_day_type_profiles() -> None:
    """Render three separate profile editors for weekday, Saturday, Sunday."""
    tabs = st.tabs(["Mo-Fr", "Sa", "So/Feiertag"])

    with tabs[0]:
        st.caption("Werktage (Mo-Fr)")
        _render_profile_editor("_active_base", "profile_editor_weekday")

    with tabs[1]:
        st.caption("Samstag")
        if "_profile_saturday" not in st.session_state:
            st.session_state._profile_saturday = list(PROFILE_SATURDAY)
        _render_profile_editor("_profile_saturday", "profile_editor_saturday")

    with tabs[2]:
        st.caption("Sonn- und Feiertage")
        if "_profile_sunday" not in st.session_state:
            st.session_state._profile_sunday = list(PROFILE_SUNDAY)
        _render_profile_editor("_profile_sunday", "profile_editor_sunday")


def _render_single_profile() -> None:
    """Render a single profile editor for all days."""
    _render_profile_editor("_active_base", "profile_editor")


def _render_profile_editor(state_key: str, editor_key: str) -> None:
    """
    Render a profile editor for hourly consumption values.
    
    Args:
        state_key: Session state key for the profile data
        editor_key: Unique key for the data editor widget
    """
    profile_df = pd.DataFrame({
        "Stunde": [f"{h:02d}:00" for h in range(24)],
        "Verbrauch (W)": st.session_state[state_key],
    })
    edited_df = st.data_editor(
        profile_df, disabled=["Stunde"], hide_index=True,
        width="stretch", key=editor_key,
    )
    new_values = edited_df["Verbrauch (W)"].tolist()
    if new_values != st.session_state[state_key]:
        st.session_state[state_key] = new_values
        st.rerun()


def _render_expert_profile_settings() -> None:
    """Render expert mode profile settings with CSV upload."""
    st.caption("📊 Lade dein eigenes Jahreslastprofil als CSV-Datei hoch")

    current_year = sv("cfg_year")

    # Template download section
    st.markdown("**1. Vorlage herunterladen**")
    template_csv = generate_yearly_template_csv(current_year)

    st.download_button(
        label=f"📥 Vorlage für {current_year} herunterladen",
        data=template_csv,
        file_name=f"lastprofil_vorlage_{current_year}.csv",
        mime="text/csv",
        help=f"CSV-Vorlage mit Zeitstempeln für das Jahr {current_year}. "
             "Fülle die zweite Spalte mit deinen Verbrauchsdaten in Watt.",
    )

    num_hours = get_hours_in_year(current_year)
    st.caption(f"Die Vorlage enthält {num_hours} Stunden für {current_year}.")

    # Upload section
    st.markdown("**2. Ausgefüllte Datei hochladen**")
    uploaded_file = st.file_uploader(
        "CSV-Datei hochladen",
        type=["csv"],
        key="yearly_profile_upload",
        help="Lade die ausgefüllte CSV-Datei mit deinen stündlichen Verbrauchsdaten hoch.",
    )

    # Process uploaded file
    if uploaded_file is not None:
        profile_data, error = parse_yearly_profile_csv(uploaded_file, current_year)

        if error:
            st.error(f"❌ {error}")
            st.session_state._yearly_profile = None
            st.session_state._yearly_profile_stats = None
        else:
            st.session_state._yearly_profile = profile_data
            st.session_state._yearly_profile_stats = calculate_profile_stats(profile_data)
            st.success(f"✅ Profil erfolgreich geladen ({len(profile_data)} Stunden)")

    # Show profile statistics if available
    if st.session_state.get("_yearly_profile_stats"):
        stats = st.session_state._yearly_profile_stats
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Jahresverbrauch", f"{stats['total_kwh']:.0f} kWh")
            st.metric("Min. Leistung", f"{stats['min_w']:.0f} W")
        with col2:
            st.metric("Ø Leistung", f"{stats['avg_w']:.0f} W")
            st.metric("Max. Leistung", f"{stats['max_w']:.0f} W")
    elif "_yearly_profile" not in st.session_state or st.session_state._yearly_profile is None:
        st.info("💡 Lade eine CSV-Datei mit deinen Smart-Meter-Daten hoch, um fortzufahren.")


def _render_seasonal_settings() -> None:
    """Render seasonal scaling settings (only for advanced mode)."""
    st.toggle(
        "❄️ Saisonale Skalierung", key="cfg_seasonal_enabled",
        help="Verbrauch im Winter höher, im Sommer niedriger. "
             "Das H0-Profil (Einfach-Modus) enthält bereits saisonale Unterschiede. "
             "Die Voreinstellungen ahmen die Skalierung des H0-Profils nach.",
        **widget_value("cfg_seasonal_enabled")
    )
    if sv("cfg_seasonal_enabled"):
        st.slider("Winter-Faktor (%)", 100, 130, key="cfg_season_winter",
                  **widget_value("cfg_season_winter"))
        st.slider("Sommer-Faktor (%)", 70, 100, key="cfg_season_summer",
                  **widget_value("cfg_season_summer"))
        st.caption("Apr & Okt: 100% (Übergangszeit)")


def _render_flex_load_settings() -> None:
    """Render flexible load shifting settings."""
    st.toggle(
        "☀️ Lastverschiebung an Sonnentagen", key="cfg_flex_enabled",
        help="Zusätzlicher Verbrauch **nur an ertragreichen Tagen** (z. B. Waschmaschine). "
             "Wird nur ausgelöst, wenn genug PV-Ertrag erwartet wird.",
        **widget_value("cfg_flex_enabled")
    )
    if sv("cfg_flex_enabled"):
        st.caption("Zusätzliche Last pro Stunde an Sonnentagen (Watt)")
        flex_df = pd.DataFrame({
            "Stunde": [f"{h:02d}:00" for h in range(24)],
            "Δ Last (W)": st.session_state._flex_delta,
        })
        edited_flex = st.data_editor(
            flex_df, disabled=["Stunde"], hide_index=True,
            width="stretch", key="flex_editor",
        )
        new_flex = edited_flex["Δ Last (W)"].tolist()
        if new_flex != st.session_state._flex_delta:
            st.session_state._flex_delta = new_flex
            st.rerun()
        st.number_input(
            "Min. Tagesertrag zum Auslösen (kWh)", step=0.5, format="%.1f",
            key="cfg_flex_min_yield",
            **widget_value("cfg_flex_min_yield")
        )
        st.number_input(
            "Max. Einsätze im Vorrat", step=1, min_value=1,
            key="cfg_flex_pool",
            help="Wird aufgefüllt wenn nicht ausgelöst, max. dieses Limit. "
                 "Beispiel Waschmaschine: wie viele Maschinen max. hintereinander, bis keine Wäsche mehr da ist?",
            **widget_value("cfg_flex_pool")
        )
        st.number_input(
            "Auffrischungsrate (pro Tag)", step=0.1, min_value=0.0,
            format="%.1f", key="cfg_flex_refresh",
            help="Einsätze die jeden Tag zum Vorrat hinzugefügt werden. "
                 "Beispiel Waschmaschine: Jeden Tag fällt neue Wäsche an. "
                 "Bei 0,5 kann nach 2 Tagen ein neuer Waschgang durchgeführt werden.",
            **widget_value("cfg_flex_refresh")
        )


def _render_periodic_load_settings() -> None:
    """Render periodic load settings."""
    st.toggle(
        "🔄 Periodische Zusatzlast", key="cfg_periodic_enabled",
        help="Regelmäßiger Zusatzverbrauch **unabhängig vom Wetter** "
             "(z. B. 🌡️ Warmwasser-Desinfektion). "
             "Wird in festen Intervallen ausgelöst.",
        **widget_value("cfg_periodic_enabled")
    )
    if sv("cfg_periodic_enabled"):
        st.number_input(
            "Intervall (Tage)", step=1, min_value=1, key="cfg_periodic_days",
            help="Wie oft die Zusatzlast auftritt (z.B. alle 3 Tage)",
            **widget_value("cfg_periodic_days")
        )
        st.caption("Zusatzlast pro Stunde an Ausführungstagen (Watt)")
        periodic_df = pd.DataFrame({
            "Stunde": [f"{h:02d}:00" for h in range(24)],
            "Δ Last (W)": st.session_state._periodic_delta,
        })
        edited_periodic = st.data_editor(
            periodic_df, disabled=["Stunde"], hide_index=True,
            width="stretch", key="periodic_editor",
        )
        new_periodic = edited_periodic["Δ Last (W)"].tolist()
        if new_periodic != st.session_state._periodic_delta:
            st.session_state._periodic_delta = new_periodic
            st.rerun()

