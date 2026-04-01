"""
Session state management and URL configuration sharing for the PV analysis application.
"""
import base64
import json
import zlib
import streamlit as st

from config import (
    CONFIG_KEYS_SIMPLE, PERSISTED_KEYS, PROFILE_BASE, DEFAULT_ANNUAL_KWH,
    FLEX_DELTA_DEFAULT, PERIODIC_DELTA_DEFAULT, DEFAULT_MODULES, DEFAULT_STORAGES,
    SESSION_STATE_DEFAULTS
)


def encode_config() -> str:
    """Collect current config from session state and encode as URL-safe base64 string."""
    data = {}
    for k in CONFIG_KEYS_SIMPLE:
        if k in st.session_state:
            data[k] = st.session_state[k]
    data["modules"] = st.session_state.modules
    data["storages"] = st.session_state.storages
    data["next_mod_id"] = st.session_state.next_mod_id
    data["next_stor_id"] = st.session_state.next_stor_id
    data["_active_base"] = st.session_state._active_base
    data["_flex_delta"] = st.session_state._flex_delta
    data["_periodic_delta"] = st.session_state._periodic_delta
    # Add day-type profiles if enabled
    if st.session_state.get("cfg_use_day_types", False):
        data["cfg_use_day_types"] = True
        if "_profile_saturday" in st.session_state:
            data["_profile_saturday"] = st.session_state._profile_saturday
        if "_profile_sunday" in st.session_state:
            data["_profile_sunday"] = st.session_state._profile_sunday
    # Add version for future compatibility
    data["_version"] = 2
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    return base64.urlsafe_b64encode(compressed).decode("ascii")


def decode_config(encoded: str) -> None:
    """Decode a base64 config string and restore into session state."""
    compressed = base64.urlsafe_b64decode(encoded)
    raw = zlib.decompress(compressed)
    data = json.loads(raw)
    
    # Check version for future migrations
    version = data.get("_version", 0)
    
    for k in CONFIG_KEYS_SIMPLE:
        if k in data:
            st.session_state[k] = data[k]
    if "modules" in data:
        st.session_state.modules = data["modules"]
        st.session_state.next_mod_id = data.get("next_mod_id", len(data["modules"]))
    if "storages" in data:
        st.session_state.storages = data["storages"]
        st.session_state.next_stor_id = data.get("next_stor_id", len(data["storages"]))
    if "_active_base" in data:
        st.session_state._active_base = data["_active_base"]
    if "_flex_delta" in data:
        st.session_state._flex_delta = data["_flex_delta"]
    if "_periodic_delta" in data:
        st.session_state._periodic_delta = data["_periodic_delta"]
    # Restore day-type profiles (version 2+)
    if data.get("cfg_use_day_types", False):
        st.session_state.cfg_use_day_types = True
        if "_profile_saturday" in data:
            st.session_state._profile_saturday = data["_profile_saturday"]
        if "_profile_sunday" in data:
            st.session_state._profile_sunday = data["_profile_sunday"]


def init_session_state() -> None:
    """Initialize session state with default values."""
    # Restore config from URL on first load
    if "_config_loaded" not in st.session_state:
        st.session_state._config_loaded = True
        cfg_param = st.query_params.get("cfg")
        if cfg_param:
            try:
                decode_config(cfg_param)
            except Exception:
                st.toast("Ungültiger Konfigurations-Link – Standardwerte werden verwendet.")

    # Initialize modules
    if "modules" not in st.session_state:
        st.session_state.next_mod_id = 1
        st.session_state.modules = list(DEFAULT_MODULES)

    # Initialize storages
    if "storages" not in st.session_state:
        st.session_state.next_stor_id = 3
        st.session_state.storages = list(DEFAULT_STORAGES)

    # Initialize consumption profiles
    if "_active_base" not in st.session_state:
        st.session_state._active_base = list(PROFILE_BASE)
    if "_flex_delta" not in st.session_state:
        st.session_state._flex_delta = list(FLEX_DELTA_DEFAULT)
    if "_periodic_delta" not in st.session_state:
        st.session_state._periodic_delta = list(PERIODIC_DELTA_DEFAULT)

    # Persist widget values when expanders are collapsed
    for _k in PERSISTED_KEYS:
        _bk = f"_bak_{_k}"
        if _k in st.session_state:
            st.session_state[_bk] = st.session_state[_k]
        elif _bk in st.session_state:
            st.session_state[_k] = st.session_state[_bk]


def sv(key: str, default=None):
    """
    Read a value from session state with a fallback default.
    
    If default is None, looks up the centralized default from SESSION_STATE_DEFAULTS.
    """
    if default is None:
        default = SESSION_STATE_DEFAULTS.get(key)
    return st.session_state.get(key, default)


def widget_value(key: str, default=None) -> dict:
    """Return dict with 'value' only if key not already in session state.
    
    This prevents 'widget created with default value but also had value set via Session State API' errors
    when values are restored from deep links or other session state manipulations.
    
    If default is None, looks up the centralized default from SESSION_STATE_DEFAULTS.
    """
    if key in st.session_state:
        return {}
    if default is None:
        default = SESSION_STATE_DEFAULTS.get(key)
    return {"value": default}


def scale_profile_to_annual_kwh(annual_kwh: float) -> list[int]:
    """Scale the base consumption profile to match the desired annual consumption."""
    scale = annual_kwh / DEFAULT_ANNUAL_KWH
    return [round(w * scale) for w in PROFILE_BASE]
