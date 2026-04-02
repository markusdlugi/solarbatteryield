"""
Sidebar UI components for the PV analysis application.
Contains all configuration widgets and input controls.
"""
import pandas as pd
import streamlit as st

from config import PROFILE_SATURDAY, PROFILE_SUNDAY, DEFAULTS, LIMITS, scale_profiles
from api import geocode, reverse_geocode, GeocodingError
from inverter_efficiency import (
    DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT,
    INVERTER_EFFICIENCY_CURVES,
)
from state import sv, widget_value


def render_sidebar() -> None:
    """Render the complete sidebar with all configuration sections."""
    st.sidebar.header("⚙️ Parameter")
    
    _render_location_section()
    _render_consumption_section()
    _render_pv_system_section()
    _render_storage_section()
    _render_prices_section()


def _render_location_section() -> None:
    """Render the location configuration section."""
    with st.sidebar.expander("📍 Standort", expanded=True):
        location_query = st.text_input(
            "🔍 Ort suchen", value="", key="cfg_location_query",
            placeholder="z. B. München, Berlin …",
            help="Sucht Koordinaten via OpenStreetMap.",
        )
        if location_query:
            try:
                result = geocode(location_query)
                if result:
                    display_name, found_lat, found_lon = result
                    st.session_state._location_display_name = display_name
                    if "cfg_lat" not in st.session_state or st.session_state.get("_last_geo_query") != location_query:
                        st.session_state.cfg_lat = found_lat
                        st.session_state.cfg_lon = found_lon
                        st.session_state._last_geo_query = location_query
                        st.rerun()
                else:
                    st.warning("Ort nicht gefunden.")
                    st.session_state._location_display_name = None
            except GeocodingError as e:
                st.error(f"⚠️ {e}")
                st.session_state._location_display_name = None

        if "cfg_lat" not in st.session_state:
            st.session_state.cfg_lat = None
        if "cfg_lon" not in st.session_state:
            st.session_state.cfg_lon = None

        st.number_input("Breitengrad", format="%.4f", key="cfg_lat",
                        placeholder="z. B. 48.1371")
        st.number_input("Längengrad", format="%.4f", key="cfg_lon",
                        placeholder="z. B. 11.5754")

        _lat, _lon = sv("cfg_lat", None), sv("cfg_lon", None)
        if _lat is not None and _lon is not None:
            if not location_query:
                _coord_key = f"{_lat:.4f},{_lon:.4f}"
                if st.session_state.get("_reverse_geo_key") != _coord_key:
                    _place_name = reverse_geocode(_lat, _lon)
                    st.session_state._reverse_geo_key = _coord_key
                    st.session_state._location_display_name = _place_name
            _place_name = st.session_state.get("_location_display_name")
            if _place_name:
                st.caption(f"📍 {_place_name}")


def _render_consumption_section() -> None:
    """Render the consumption configuration section."""
    with st.sidebar.expander("💡 Verbrauch"):
        _profile_modes = ["Einfach", "Erweitert"]
        st.radio(
            "Lastprofil-Modus", _profile_modes, horizontal=True,
            index=_profile_modes.index(sv("cfg_profile_mode")),
            key="cfg_profile_mode",
            help="**Einfach**: BDEW H0-Standardlastprofil mit Unterscheidung nach Wochentag/Samstag/Sonntag. "
                 "**Erweitert**: Eigenes stündliches Lastprofil mit optionaler Saisonskalierung.",
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
            st.number_input(
                "Jahresverbrauch (kWh)", value=sv("cfg_annual_kwh"), step=100,
                min_value=LIMITS.annual_kwh_min, key="cfg_annual_kwh",
                placeholder="z. B. 3000",
            )
            st.caption("📊 Das BDEW H0-Standardlastprofil berücksichtigt automatisch "
                      "unterschiedliche Verbräuche an Werktagen, Samstagen und Sonn-/Feiertagen "
                      "sowie saisonale Unterschiede.")
        else:
            _render_advanced_profile_settings()
            _render_seasonal_settings()

        _render_flex_load_settings()
        _render_periodic_load_settings()


def _render_advanced_profile_settings() -> None:
    """Render advanced profile settings with optional day-type differentiation."""
    st.caption("Verbrauch in Watt für jede Stunde eines typischen Tages")
    
    # Check if day-type profiles are enabled
    use_day_types = st.toggle(
        "📅 Tagtyp-Differenzierung", 
        key="cfg_use_day_types",
        help="Separate Profile für Werktage, Samstage und Sonn-/Feiertage",
        **widget_value("cfg_use_day_types", False),
    )
    
    if use_day_types:
        # Three separate editors for weekday, Saturday, Sunday
        tabs = st.tabs(["Mo-Fr", "Sa", "So/Feiertag"])
        
        with tabs[0]:
            st.caption("Werktage (Mo-Fr)")
            profile_df = pd.DataFrame({
                "Stunde": [f"{h:02d}:00" for h in range(24)],
                "Verbrauch (W)": st.session_state._active_base,
            })
            edited_df = st.data_editor(
                profile_df, disabled=["Stunde"], hide_index=True,
                use_container_width=True, key="profile_editor_weekday",
            )
            new_values = edited_df["Verbrauch (W)"].tolist()
            if new_values != st.session_state._active_base:
                st.session_state._active_base = new_values
                st.rerun()
        
        with tabs[1]:
            st.caption("Samstag")
            # Initialize Saturday profile if not exists
            if "_profile_saturday" not in st.session_state:
                st.session_state._profile_saturday = list(PROFILE_SATURDAY)
            profile_sat_df = pd.DataFrame({
                "Stunde": [f"{h:02d}:00" for h in range(24)],
                "Verbrauch (W)": st.session_state._profile_saturday,
            })
            edited_sat_df = st.data_editor(
                profile_sat_df, disabled=["Stunde"], hide_index=True,
                use_container_width=True, key="profile_editor_saturday",
            )
            new_sat_values = edited_sat_df["Verbrauch (W)"].tolist()
            if new_sat_values != st.session_state._profile_saturday:
                st.session_state._profile_saturday = new_sat_values
                st.rerun()
        
        with tabs[2]:
            st.caption("Sonn- und Feiertage")
            # Initialize Sunday profile if not exists
            if "_profile_sunday" not in st.session_state:
                st.session_state._profile_sunday = list(PROFILE_SUNDAY)
            profile_sun_df = pd.DataFrame({
                "Stunde": [f"{h:02d}:00" for h in range(24)],
                "Verbrauch (W)": st.session_state._profile_sunday,
            })
            edited_sun_df = st.data_editor(
                profile_sun_df, disabled=["Stunde"], hide_index=True,
                use_container_width=True, key="profile_editor_sunday",
            )
            new_sun_values = edited_sun_df["Verbrauch (W)"].tolist()
            if new_sun_values != st.session_state._profile_sunday:
                st.session_state._profile_sunday = new_sun_values
                st.rerun()
    else:
        # Single profile for all days
        profile_df = pd.DataFrame({
            "Stunde": [f"{h:02d}:00" for h in range(24)],
            "Verbrauch (W)": st.session_state._active_base,
        })
        edited_df = st.data_editor(
            profile_df, disabled=["Stunde"], hide_index=True,
            use_container_width=True, key="profile_editor",
        )
        new_values = edited_df["Verbrauch (W)"].tolist()
        if new_values != st.session_state._active_base:
            st.session_state._active_base = new_values
            st.rerun()



def _render_seasonal_settings() -> None:
    """Render seasonal scaling settings (only for advanced mode)."""
    st.toggle("❄️ Saisonale Skalierung", key="cfg_seasonal_enabled",
        help="Verbrauch im Winter höher, im Sommer niedriger. "
             "Das H0-Profil (Einfach-Modus) enthält bereits saisonale Unterschiede. "
             "Die Voreinstellungen ahmen die Skalierung des H0-Profils nach.",
        **widget_value("cfg_seasonal_enabled"))
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
        **widget_value("cfg_flex_enabled"))
    if sv("cfg_flex_enabled"):
        st.caption("Zusätzliche Last pro Stunde an Sonnentagen (Watt)")
        flex_df = pd.DataFrame({
            "Stunde": [f"{h:02d}:00" for h in range(24)],
            "Δ Last (W)": st.session_state._flex_delta,
        })
        edited_flex = st.data_editor(
            flex_df, disabled=["Stunde"], hide_index=True,
            use_container_width=True, key="flex_editor",
        )
        new_flex = edited_flex["Δ Last (W)"].tolist()
        if new_flex != st.session_state._flex_delta:
            st.session_state._flex_delta = new_flex
            st.rerun()
        st.number_input(
            "Min. Tagesertrag zum Auslösen (kWh)", step=0.5, format="%.1f",
            key="cfg_flex_min_yield",
            **widget_value("cfg_flex_min_yield"))
        st.number_input(
            "Max. Einsätze im Vorrat", step=1, min_value=1,
            key="cfg_flex_pool",
            help="Wird aufgefüllt wenn nicht ausgelöst, max. dieses Limit. "
                 "Beispiel Waschmaschine: wie viele Maschinen max. hintereinander, bis keine Wäsche mehr da ist?",
            **widget_value("cfg_flex_pool"))
        st.number_input(
            "Auffrischungsrate (pro Tag)", step=0.1, min_value=0.0,
            format="%.1f", key="cfg_flex_refresh",
            help="Einsätze die pro Nicht-Flex-Tag zum Vorrat hinzugefügt werden. "
                 "Beispiel Waschmaschine: wie lange dauert es, bis ein neuer Waschgang durchgeführt werden kann "
                 "(bei 0,5 also 2 Tage)?",
            **widget_value("cfg_flex_refresh"))


def _render_periodic_load_settings() -> None:
    """Render periodic load settings."""
    st.toggle(
        "🔄 Periodische Zusatzlast", key="cfg_periodic_enabled",
        help="Regelmäßiger Zusatzverbrauch **unabhängig vom Wetter** "
             "(z. B. 🌡️ Warmwasser-Desinfektion). "
             "Wird in festen Intervallen ausgelöst.",
        **widget_value("cfg_periodic_enabled"))
    if sv("cfg_periodic_enabled"):
        st.number_input(
            "Intervall (Tage)", step=1, min_value=1, key="cfg_periodic_days",
            **widget_value("cfg_periodic_days"))
        st.caption("Zusatzlast pro Stunde an Ausführungstagen (Watt)")
        periodic_df = pd.DataFrame({
            "Stunde": [f"{h:02d}:00" for h in range(24)],
            "Δ Last (W)": st.session_state._periodic_delta,
        })
        edited_periodic = st.data_editor(
            periodic_df, disabled=["Stunde"], hide_index=True,
            use_container_width=True, key="periodic_editor",
        )
        new_periodic = edited_periodic["Δ Last (W)"].tolist()
        if new_periodic != st.session_state._periodic_delta:
            st.session_state._periodic_delta = new_periodic
            st.rerun()


def _render_pv_system_section() -> None:
    """Render the PV system configuration section."""
    with st.sidebar.expander("⚡ PV-System"):
        _year_options = list(range(LIMITS.year_min, LIMITS.year_max + 1))
        st.selectbox("PVGIS-Datenjahr", _year_options,
                     index=_year_options.index(sv("cfg_year")), key="cfg_year",
                     help="Das Jahr für die Analyse. 2015 war ein gutes Durchschnittsjahr.")
        st.slider("PV System-Verluste (%)", LIMITS.loss_min, LIMITS.loss_max, key="cfg_loss",
                  help="Verluste durch Kabel, Verschmutzung, Temperatur, Mismatch etc. "
                       "**Ohne Wechselrichterverluste**, da diese separat berechnet werden (s.u.), "
                       "daher etwas niedriger als PVGIS-Empfehlung von 14%.",
                  **widget_value("cfg_loss"))
        
        # Inverter efficiency curve selection
        _render_inverter_efficiency_section()
        
        st.toggle(
            "⚡ Wechselrichter-Limit", key="cfg_inverter_limit_enabled",
            **widget_value("cfg_inverter_limit_enabled"))
        if sv("cfg_inverter_limit_enabled"):
            st.number_input(
                "Wechselrichter-Limit (W)", step=100, 
                min_value=LIMITS.inverter_limit_w_min,
                key="cfg_inverter_limit_w",
                help="Maximale AC-Ausgangsleistung des Wechselrichters in Watt.",
                **widget_value("cfg_inverter_limit_w"))
        st.number_input("Kosten PV-System ohne Speicher (€)", step=50, key="cfg_base_cost",
                        **widget_value("cfg_base_cost"))
        st.divider()
        _render_modules_config()


def _render_inverter_efficiency_section() -> None:
    """Render inverter efficiency curve selection and custom curve editor."""
    # Efficiency preset options
    _preset_options = {
        "pessimistic": "🔻 Pessimistisch (P10)",
        "median": "📊 Durchschnittlich (P50)",
        "optimistic": "🔺 Optimistisch (P90)",
        "custom": "⚙️ Benutzerdefiniert",
    }
    
    # Initialize preset if not in session state
    if "cfg_inverter_efficiency_preset" not in st.session_state:
        st.session_state.cfg_inverter_efficiency_preset = "median"
    
    current_preset = sv("cfg_inverter_efficiency_preset")
    preset_index = list(_preset_options.keys()).index(current_preset) if current_preset in _preset_options else 1
    
    st.selectbox(
        "📈 WR-Wirkungsgradkurve",
        options=list(_preset_options.keys()),
        format_func=lambda x: _preset_options[x],
        index=preset_index,
        key="cfg_inverter_efficiency_preset",
        help="Wirkungsgrad des Wechselrichters variiert mit der Leistung. "
             "Basierend auf CEC-Daten (California Energy Commission) von ~3.000 Wechselrichtern. "
             "P10 = 10. Perzentil (konservativ), P50 = Median (typisch), P90 = 90. Perzentil (Premium-Geräte).",
    )
    
    # Show custom curve editor if custom is selected
    if sv("cfg_inverter_efficiency_preset") == "custom":
        _render_custom_efficiency_editor()
    else:
        # Show the current curve values as info
        _show_efficiency_curve_info(sv("cfg_inverter_efficiency_preset"))


def _render_custom_efficiency_editor() -> None:
    """Render the custom efficiency curve editor."""
    # Initialize custom values if not present
    if "_inverter_eff_custom" not in st.session_state:
        st.session_state._inverter_eff_custom = list(DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT)
    
    st.caption("Wirkungsgrad (%) bei verschiedenen Leistungsstufen")
    
    power_levels = [10, 20, 30, 50, 75, 100]
    
    # Create a dataframe for editing
    eff_df = pd.DataFrame({
        "Leistung (%)": [f"{p}%" for p in power_levels],
        "Wirkungsgrad (%)": st.session_state._inverter_eff_custom,
    })
    
    edited_eff = st.data_editor(
        eff_df,
        disabled=["Leistung (%)"],
        hide_index=True,
        use_container_width=True,
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
    
    st.caption("💡 Tipp: CEC-Wechselrichterdaten unter [energy.ca.gov](https://www.energy.ca.gov/programs-and-topics/programs/solar-equipment-lists) prüfen")


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


def _render_modules_config() -> None:
    """Render PV modules configuration."""
    st.markdown("**Module**")
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


def _render_storage_section() -> None:
    """Render the storage configuration section."""
    with st.sidebar.expander("🔋 Speicher"):
        _coupling_options = ["DC-gekoppelt", "AC-gekoppelt"]
        st.radio(
            "Speicheranbindung", _coupling_options, horizontal=True,
            index=_coupling_options.index(sv("cfg_dc_coupled")),
            key="cfg_dc_coupled",
            help="**DC-gekoppelt**: Batterie lädt ohne Limit direkt von den Panels - "
                 "Wechselrichter-Limit gilt nur für die AC-Seite. "
                 "**AC-gekoppelt**: Batterie lädt mit Limit von AC – "
                 "Wechselrichter-Limit begrenzt den gesamten PV-Ertrag."
        )
        st.slider("Lade-/Entladeverluste (%)", LIMITS.batt_loss_min, LIMITS.batt_loss_max, 
                  key="cfg_batt_loss",
                  **widget_value("cfg_batt_loss"))
        st.slider("Min. Ladezustand Sommer (%)", LIMITS.soc_min, LIMITS.soc_max, 
                  key="cfg_min_soc_s",
                  **widget_value("cfg_min_soc_s"))
        st.slider("Max. Ladezustand Sommer (%)", LIMITS.soc_min, LIMITS.soc_max, 
                  key="cfg_max_soc_s",
                  **widget_value("cfg_max_soc_s"))
        st.slider("Min. Ladezustand Winter (%)", LIMITS.soc_min, LIMITS.soc_max, 
                  key="cfg_min_soc_w",
                  **widget_value("cfg_min_soc_w"))
        st.slider("Max. Ladezustand Winter (%)", LIMITS.soc_min, LIMITS.soc_max, 
                  key="cfg_max_soc_w",
                  **widget_value("cfg_max_soc_w"))
        st.divider()
        _render_storages_config()


def _render_storages_config() -> None:
    """Render storage options configuration."""
    st.markdown("**Ausbaustufen**")
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
            if st.button("🗑️ Speicher entfernen", key=f"sd_{sid}"):
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


def _render_prices_section() -> None:
    """Render the prices and comparison section."""
    with st.sidebar.expander("💰 Preise & Vergleich"):
        st.number_input("Strompreis (€/kWh)", step=0.01, format="%.2f", key="cfg_e_price",
                        min_value=LIMITS.e_price_min, max_value=LIMITS.e_price_max,
                        **widget_value("cfg_e_price"))
        st.number_input(
            "Strompreis-Steigerung (%/a)", step=0.5, format="%.1f", key="cfg_e_inc",
            min_value=LIMITS.e_inc_min, max_value=LIMITS.e_inc_max,
            **widget_value("cfg_e_inc"))
        st.number_input(
            "Einspeisevergütung (ct/kWh)", step=0.5, min_value=0.0,
            format="%.1f", key="cfg_feed_in_tariff",
            help="Vergütung für ins Netz eingespeisten Strom. "
                 "In Deutschland aktuell ca. 8,0 ct/kWh für Anlagen bis 10 kWp. "
                 "Bei Balkonkraftwerken in der Regel keine Vergütung aufgrund vereinfachter Anmeldung.",
            **widget_value("cfg_feed_in_tariff"))
        st.number_input(
            "ETF-Rendite (%/a)", step=0.5, format="%.1f", key="cfg_etf_ret",
            help="Angenommene Rendite eines beispielhaften ETF als alternatives Investment.",
            min_value=LIMITS.etf_ret_min, max_value=LIMITS.etf_ret_max,
            **widget_value("cfg_etf_ret"))
        st.slider("Analyse-Horizont (Jahre)", LIMITS.years_min, LIMITS.years_max, 
                  key="cfg_years",
                  **widget_value("cfg_years"))

