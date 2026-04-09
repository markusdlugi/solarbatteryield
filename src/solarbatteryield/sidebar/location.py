"""
Location configuration section of the sidebar.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.api import geocode, reverse_geocode, GeocodingError
from solarbatteryield.state import sv


def render_location_section() -> None:
    """
    Render the location configuration section.
    
    Provides:
    - Location search via geocoding
    - Manual lat/lon input
    - Reverse geocoding for manual coordinates
    """
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
                    display_name, short_place_name, found_lat, found_lon = result
                    st.session_state._location_display_name = short_place_name
                    if st.session_state.get("_last_geo_query") != location_query:
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

