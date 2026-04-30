"""
Core sidebar component that orchestrates all sidebar sections.
"""
from __future__ import annotations

import streamlit as st

from solarbatteryield.sidebar.location import render_location_section
from solarbatteryield.sidebar.consumption import render_consumption_section
from solarbatteryield.sidebar.pv_config import render_pv_modules_section, render_pv_config_section
from solarbatteryield.sidebar.storage_config import render_storage_options_section, render_storage_config_section
from solarbatteryield.sidebar.prices import render_prices_section
from solarbatteryield.state import is_shared_url_visit, mark_user_modified


def render_sidebar() -> None:
    """
    Render the complete sidebar with all configuration sections.
    
    Sections rendered in order:
    1. Location (coordinates/geocoding)
    2. Consumption (profile mode, annual consumption)
    3. PV Modules (module configuration)
    4. PV Configuration (system settings)
    5. Storage Options (battery configurations)
    6. Storage Configuration (battery settings)
    7. Prices & Comparison (economic parameters)
    """
    # Mark config as modified on any rerun after initial load from shared URL.
    # On the very first render _sidebar_rendered is not yet set; subsequent
    # reruns (triggered by widget interaction) will mark the config modified.
    if is_shared_url_visit():
        if st.session_state.get("_sidebar_rendered", False):
            mark_user_modified()
        else:
            st.session_state._sidebar_rendered = True

    st.sidebar.header("⚙️ Parameter")

    render_location_section()
    render_consumption_section()
    render_pv_modules_section()
    render_pv_config_section()
    render_storage_options_section()
    render_storage_config_section()
    render_prices_section()

