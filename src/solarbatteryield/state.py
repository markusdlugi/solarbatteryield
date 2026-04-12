"""
Session state management and URL configuration sharing for the PV analysis application.
"""
import base64
import copy
import json
import zlib

import streamlit as st

from solarbatteryield.config import (
    CONFIG_KEYS_SIMPLE, PERSISTED_KEYS, LAZY_INIT_KEYS, PROFILE_BASE,
    FLEX_DELTA_DEFAULT, PERIODIC_DELTA_DEFAULT, DEFAULT_MODULES, DEFAULT_STORAGES,
    SESSION_STATE_DEFAULTS
)


def encode_config() -> str:
    """Collect current config from session state and encode as URL-safe base64 string."""
    data = {}
    for k in CONFIG_KEYS_SIMPLE:
        if k in st.session_state:
            data[k] = st.session_state[k]
        elif k in LAZY_INIT_KEYS:
            # LAZY_INIT_KEYS are popped by widget_value() before widgets render,
            # so they may only exist as backups at encoding time.
            _bak = f"_bak_{k}"
            if _bak in st.session_state:
                data[k] = st.session_state[_bak]
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
    # Add custom inverter efficiency curve if using custom preset
    if st.session_state.get("cfg_inverter_efficiency_preset") == "custom":
        if "_inverter_eff_custom" in st.session_state:
            data["_inverter_eff_custom"] = st.session_state._inverter_eff_custom
    # Add custom battery inverter efficiency curve if using custom preset
    if st.session_state.get("cfg_batt_inverter_preset") == "custom":
        if "_batt_inverter_eff_custom" in st.session_state:
            data["_batt_inverter_eff_custom"] = st.session_state._batt_inverter_eff_custom
    # Add discharge time windows if using time_window strategy
    if st.session_state.get("cfg_discharge_strategy") == "time_window":
        if "_discharge_time_windows" in st.session_state:
            data["_discharge_time_windows"] = st.session_state._discharge_time_windows
    # Add version for future compatibility
    data["_version"] = 5
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
    # Restore custom inverter efficiency curve (version 3+)
    if "_inverter_eff_custom" in data:
        st.session_state._inverter_eff_custom = data["_inverter_eff_custom"]
    # Restore custom battery inverter efficiency curve (version 4+)
    if "_batt_inverter_eff_custom" in data:
        st.session_state._batt_inverter_eff_custom = data["_batt_inverter_eff_custom"]
    # Restore discharge time windows (version 5+)
    if "_discharge_time_windows" in data:
        st.session_state._discharge_time_windows = data["_discharge_time_windows"]


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

    # Pre-initialize all config keys with their defaults to avoid
    # "dictionary changed size during iteration" errors when widgets
    # try to initialize them during render.
    # Exception: LAZY_INIT_KEYS are skipped here so that widget_value()
    # can pass their default as an explicit 'value' parameter on first
    # render – this prevents Streamlit from ignoring the intended default
    # when it creates a conditionally-rendered widget for the first time.
    for key, default in SESSION_STATE_DEFAULTS.items():
        if key not in st.session_state and key not in LAZY_INIT_KEYS:
            st.session_state[key] = default

    # Initialize modules (deep copy to avoid sharing dicts between sessions)
    if "modules" not in st.session_state:
        st.session_state.next_mod_id = 1
        st.session_state.modules = copy.deepcopy(DEFAULT_MODULES)

    # Initialize storages (deep copy to avoid sharing dicts between sessions)
    if "storages" not in st.session_state:
        st.session_state.next_stor_id = 3
        st.session_state.storages = copy.deepcopy(DEFAULT_STORAGES)

    # Initialize consumption profiles
    if "_active_base" not in st.session_state:
        st.session_state._active_base = list(PROFILE_BASE)
    if "_flex_delta" not in st.session_state:
        st.session_state._flex_delta = list(FLEX_DELTA_DEFAULT)
    if "_periodic_delta" not in st.session_state:
        st.session_state._periodic_delta = list(PERIODIC_DELTA_DEFAULT)

    # Track profile mode for detecting Einfach → Erweitert switches
    if "_prev_profile_mode" not in st.session_state:
        st.session_state._prev_profile_mode = sv("cfg_profile_mode")

    # Persist widget values when expanders are collapsed.
    # For LAZY_INIT_KEYS: only backup, do NOT restore into session state.
    # Restoring would cause widget_value() to return {} and Streamlit would
    # ignore the value on re-render.  Instead, widget_value() / selectbox_index()
    # read the backup directly when the key is missing from session state.
    for _k in PERSISTED_KEYS:
        _bk = f"_bak_{_k}"
        if _k in st.session_state:
            st.session_state[_bk] = st.session_state[_k]
        elif _bk in st.session_state and _k not in LAZY_INIT_KEYS:
            st.session_state[_k] = st.session_state[_bk]


def sv(key: str, default=None):
    """
    Read a value from session state with a fallback default.
    
    Lookup order:
    1. Session state (widget-managed value)
    2. Backup from persistence mechanism (for conditionally rendered widgets)
    3. Centralized default from SESSION_STATE_DEFAULTS
    4. Explicit default parameter
    """
    if key in st.session_state:
        return st.session_state[key]
    _bak = f"_bak_{key}"
    if _bak in st.session_state:
        return st.session_state[_bak]
    if default is None:
        default = SESSION_STATE_DEFAULTS.get(key)
    return default


def widget_value(key: str, default=None) -> dict:
    """Return dict with 'value' for widget initialisation.
    
    For normal keys: returns 'value' only when the key is absent from session state
    (prevents Streamlit's "default value vs session state" error).
    
    For LAZY_INIT_KEYS (conditionally rendered widgets): the key is *always* popped
    from session state and returned as an explicit 'value'.  This is necessary because
    Streamlit does not reliably apply session-state values to widgets that reappear
    after having been hidden.  By popping the key we force Streamlit to treat the
    widget as new and honour the provided default.
    """
    if key in st.session_state:
        if key in LAZY_INIT_KEYS:
            val = st.session_state.pop(key)
            st.session_state[f"_bak_{key}"] = val  # keep backup current
            return {"value": val}
        return {}
    # Key not in session state – check backup, then fall back to default
    _bak = f"_bak_{key}"
    if _bak in st.session_state:
        return {"value": st.session_state[_bak]}
    if default is None:
        default = SESSION_STATE_DEFAULTS.get(key)
    return {"value": default}


def selectbox_index(key: str, options: list, default=None) -> dict:
    """Return dict with 'index' for selectbox/radio widget initialisation.
    
    Same pop-semantics as widget_value() for LAZY_INIT_KEYS.
    """
    if key in st.session_state:
        if key in LAZY_INIT_KEYS:
            val = st.session_state.pop(key)
            st.session_state[f"_bak_{key}"] = val
            try:
                return {"index": options.index(val)}
            except (ValueError, TypeError):
                pass
        else:
            return {}
    # Key not in session state – check backup, then fall back to default
    _bak = f"_bak_{key}"
    if _bak in st.session_state:
        val = st.session_state[_bak]
        try:
            return {"index": options.index(val)}
        except (ValueError, TypeError):
            pass
    if default is None:
        default = SESSION_STATE_DEFAULTS.get(key)
    try:
        index = options.index(default) if default in options else 0
    except (ValueError, TypeError):
        index = 0
    return {"index": index}


# Alias for radio buttons which use the same 'index' parameter as selectbox
radio_index = selectbox_index
