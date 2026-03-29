import altair as alt
import base64
import json
import numpy as np
import pandas as pd
import requests
import streamlit as st
import zlib

st.set_page_config(page_title="PV & Speicher Analyse", page_icon="☀️", layout="wide")

# ─── Default consumption profiles (Watt per hour 0–23) ─────────
# BDEW H0 Standardlastprofil (Haushalt), Jahresdurchschnitt über alle Monate,
# normiert auf ca. 3000 kWh/Jahr (durchschnittlicher deutscher Haushalt).
PROFILE_BASE = [
    209, 156, 135, 129, 130, 148,     # 00-05: Nacht (Grundlast)
    239, 335, 388, 416, 425, 445,     # 06-11: Morgen (Frühstück, Arbeitsbeginn)
    481, 454, 394, 355, 342, 389,     # 12-17: Mittag/Nachmittag
    475, 537, 504, 444, 390, 298,     # 18-23: Abend (Hauptverbrauchszeit)
]
_DEFAULT_ANNUAL_KWH = sum(PROFILE_BASE) / 1000 * 365  # ≈ 3000 kWh/a


def get_season(month):
    """Return season name for a given month (1-12)."""
    if month in (11, 12, 1, 2, 3):
        return "winter"
    elif month in (5, 6, 7, 8, 9):
        return "summer"
    else:  # 4, 10
        return "transition"


FLEX_DELTA_DEFAULT = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 110, 160, 0, 0, 410, 530, 0, 0, 0, 0, 0, 0, 0,
]

PERIODIC_DELTA_DEFAULT = [
    350, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
]

# ─── Sharing: encode / decode config as URL parameter ───────────
CONFIG_KEYS_SIMPLE = [
    "cfg_lat", "cfg_lon",
    "cfg_year", "cfg_loss",
    "cfg_inverter_limit_enabled", "cfg_inverter_limit_w",
    "cfg_feed_in_tariff",
    "cfg_dc_coupled", "cfg_inverter_eff",
    "cfg_batt_loss", "cfg_min_soc_s", "cfg_max_soc_s",
    "cfg_min_soc_w", "cfg_max_soc_w", "cfg_base_cost",
    "cfg_profile_mode", "cfg_annual_kwh",
    "cfg_flex_enabled", "cfg_flex_min_yield", "cfg_flex_pool", "cfg_flex_refresh",
    "cfg_periodic_enabled", "cfg_periodic_days",
    "cfg_seasonal_enabled", "cfg_season_winter", "cfg_season_summer",
    "cfg_e_price", "cfg_e_inc", "cfg_etf_ret", "cfg_years",
]


def encode_config():
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
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    return base64.urlsafe_b64encode(compressed).decode("ascii")


def decode_config(encoded):
    """Decode a base64 config string and restore into session state."""
    compressed = base64.urlsafe_b64decode(encoded)
    raw = zlib.decompress(compressed)
    data = json.loads(raw)
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


# Restore config from URL on first load
if "_config_loaded" not in st.session_state:
    st.session_state._config_loaded = True
    cfg_param = st.query_params.get("cfg")
    if cfg_param:
        try:
            decode_config(cfg_param)
        except Exception:
            st.toast("⚠️ Ungültiger Konfigurations-Link – Standardwerte werden verwendet.")

# ─── Session state defaults ─────────────────────────────────────
if "modules" not in st.session_state:
    st.session_state.next_mod_id = 1
    st.session_state.modules = [
        {"id": 0, "name": "Süd", "peak": 2.0, "azi": 0, "slope": 60},
    ]

if "storages" not in st.session_state:
    st.session_state.next_stor_id = 3
    st.session_state.storages = [
        {"id": 0, "name": "Klein", "cap": 2.0, "cost": 700},
        {"id": 1, "name": "Mittel", "cap": 4.0, "cost": 1100},
        {"id": 2, "name": "Groß", "cap": 6.0, "cost": 1500},
    ]


# ─── PVGIS data (cached) ───────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_pvgis_hourly(lat, lon, peak, slope, azi, loss, year):
    url = (
        f"https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?"
        f"lat={lat}&lon={lon}&rrad=1&use_horizon=1&peakpower={peak}&"
        f"mountingplace=free&angle={slope}&aspect={azi}&"
        f"pvcalculation=1&loss={loss}&outputformat=json&"
        f"startyear={year}&endyear={year}"
    )
    resp = requests.get(url, timeout=30)
    data = resp.json()
    if "outputs" not in data:
        raise ValueError(f"PVGIS-Fehler: {data.get('message', 'Unbekannt')}")
    return np.array([h["P"] for h in data["outputs"]["hourly"]]) / 1000


# ─── Geocoding via OpenStreetMap Nominatim ──────────────────────
@st.cache_data(show_spinner=False, ttl=86400)
def geocode(query):
    """Look up coordinates for a place name via Nominatim. Returns (display_name, lat, lon) or None."""
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 1},
        headers={"User-Agent": "pv-analyse-streamlit/1.0"},
        timeout=10,
    )
    results = resp.json()
    if results:
        r = results[0]
        return r.get("display_name", query), float(r["lat"]), float(r["lon"])
    return None


@st.cache_data(show_spinner=False, ttl=86400)
def reverse_geocode(lat, lon):
    """Reverse look-up: return a short place name for coordinates, or None."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10, "accept-language": "de"},
            headers={"User-Agent": "pv-analyse-streamlit/1.0"},
            timeout=10,
        )
        data = resp.json()
        addr = data.get("address", {})
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
        state = addr.get("state", "")
        if city:
            return f"{city}, {state}" if state else city
        return data.get("display_name", "").split(",")[0]
    except Exception:
        return None


# ─── Simulation ────────────────────────────────────────────────
def simulate(pv_raw, cap_gross, batt_loss_pct, data_year,
             inverter_limit_kw, dc_coupled, inverter_eff_pct,
             min_soc_summer_pct, min_soc_winter_pct,
             max_soc_summer_pct, max_soc_winter_pct,
             flex_load_enabled, flex_min_yield, flex_pool_size,
             flex_delta, flex_refresh_rate,
             periodic_load_enabled, periodic_delta, periodic_interval_days,
             profile_base,
             seasonal_enabled, season_winter_pct, season_summer_pct):
    hours = len(pv_raw)
    soc = 0.0
    grid_import = 0.0
    feed_in = 0.0
    total_consumption = 0.0
    curtailed = 0.0
    batt_eff = 1 - batt_loss_pct / 100
    inv_eff = inverter_eff_pct / 100  # WR-Wirkungsgrad für Batterie-Entladung (DC-gekoppelt)
    flex_pool = float(flex_pool_size)
    use_flex_today = False
    inv_cap = inverter_limit_kw if inverter_limit_kw is not None else float('inf')

    # Build seasonal factors from config
    season_factors = {
        "winter": season_winter_pct / 100 if seasonal_enabled else 1.0,
        "summer": season_summer_pct / 100 if seasonal_enabled else 1.0,
        "transition": 1.0,
    }

    # Monthly tracking
    monthly = {m: {"Direkt-PV": 0.0, "Batterie": 0.0, "Netzbezug": 0.0,
                   "Einspeisung": 0.0, "Verbrauch": 0.0, "PV-Erzeugung": 0.0}
               for m in range(1, 13)}

    for i in range(hours):
        h = i % 24
        day = i // 24

        if h == 0:
            day_yield = sum(pv_raw[i: i + 24])
            if flex_load_enabled and day_yield > flex_min_yield and flex_pool >= 1.0:
                use_flex_today = True
                flex_pool -= 1.0
            else:
                use_flex_today = False
                flex_pool = min(float(flex_pool_size), flex_pool + flex_refresh_rate)

        month = pd.to_datetime(
            i, unit="h", origin=pd.Timestamp(f"{data_year}-01-01")
        ).month
        is_winter = month in (10, 11, 12, 1, 2, 3)
        min_soc = cap_gross * (min_soc_winter_pct if is_winter else min_soc_summer_pct) / 100
        max_soc = cap_gross * (max_soc_winter_pct if is_winter else max_soc_summer_pct) / 100

        # Apply seasonal factor to base load (BDEW H0)
        season = get_season(month)
        season_factor = season_factors[season]

        load = profile_base[h] / 1000 * season_factor
        if use_flex_today:
            load += flex_delta[h] / 1000
        if periodic_load_enabled and day % periodic_interval_days == 0:
            load += periodic_delta[h] / 1000

        gen_dc = pv_raw[i]  # DC output from panels (after non-inverter losses from PVGIS)
        total_consumption += load
        monthly[month]["Verbrauch"] += load
        monthly[month]["PV-Erzeugung"] += gen_dc

        if dc_coupled:
            # ── DC-coupled: battery on DC bus, inverter limit on AC only ──
            # All DC→AC conversions go through the inverter with inv_eff losses
            # Smart inverter priority: 1) serve load  2) charge battery  3) grid export

            # Step 1: Serve household load from PV through inverter
            # Need to convert DC to AC, so we need more DC to cover AC load
            dc_needed_for_load = min(gen_dc, load / inv_eff, inv_cap / inv_eff)
            pv_to_load_ac = dc_needed_for_load * inv_eff  # AC power delivered to load
            load_deficit = load - pv_to_load_ac

            # Step 2: Charge battery from remaining DC (bypasses inverter, no inv_eff loss)
            dc_remaining = gen_dc - dc_needed_for_load
            charge = min(dc_remaining, (max_soc - soc) / batt_eff) if cap_gross > 0 else 0
            soc += charge * batt_eff
            dc_after_charge = dc_remaining - charge

            # Step 3: Export remaining DC through inverter to grid (with inv_eff loss)
            remaining_inv_dc = max(0, inv_cap / inv_eff - dc_needed_for_load)
            dc_to_export = min(dc_after_charge, remaining_inv_dc)
            export_ac = dc_to_export * inv_eff  # AC power exported to grid
            feed_in += export_ac
            curtailed += dc_after_charge - dc_to_export

            # Step 4: Cover load deficit from battery (through inverter) or grid
            # Battery discharge goes through inverter → apply batt_eff and inv_eff
            if load_deficit > 0:
                inv_headroom_dc = max(0, inv_cap / inv_eff - dc_needed_for_load - dc_to_export)
                # Combined efficiency: battery discharge * inverter
                combined_eff = batt_eff * inv_eff
                max_discharge = (
                    min(load_deficit / combined_eff, max(0, soc - min_soc),
                        inv_headroom_dc / inv_eff / batt_eff)
                    if cap_gross > 0 else 0
                )
                soc -= max_discharge
                from_batt_ac = max_discharge * combined_eff  # AC output after both losses
                from_grid = load_deficit - from_batt_ac
                grid_import += from_grid
                monthly[month]["Direkt-PV"] += pv_to_load_ac
                monthly[month]["Batterie"] += from_batt_ac
                monthly[month]["Netzbezug"] += from_grid
            else:
                monthly[month]["Direkt-PV"] += pv_to_load_ac
            monthly[month]["Einspeisung"] += export_ac
        else:
            # ── AC-coupled: inverter converts all PV to AC first, battery on AC side ──
            # The battery has its own inverter (losses included in batt_loss)
            
            # Convert DC to AC through main inverter (with inv_eff loss and inv_cap limit)
            dc_to_inverter = min(gen_dc, inv_cap / inv_eff)  # DC that can go through inverter
            gen_ac = dc_to_inverter * inv_eff  # AC output after inverter
            curtailed += gen_dc - dc_to_inverter
            
            net = gen_ac - load

            if net > 0:
                # Surplus: charge battery (AC→DC in battery inverter, loss in batt_eff)
                charge = min(net, (max_soc - soc) / batt_eff) if cap_gross > 0 else 0
                soc += charge * batt_eff
                surplus = net - charge
                feed_in += surplus
                monthly[month]["Direkt-PV"] += load
                monthly[month]["Einspeisung"] += surplus
            else:
                # Deficit: discharge battery (DC→AC in battery inverter, loss in batt_eff)
                deficit = abs(net)
                discharge = (
                    min(deficit / batt_eff, max(0, soc - min_soc))
                    if cap_gross > 0
                    else 0
                )
                soc -= discharge
                from_batt = discharge * batt_eff
                from_grid = deficit - from_batt
                grid_import += from_grid
                monthly[month]["Direkt-PV"] += gen_ac
                monthly[month]["Batterie"] += from_batt
                monthly[month]["Netzbezug"] += from_grid

    return grid_import, total_consumption, feed_in, curtailed, monthly


# ─── Long-term helpers ──────────────────────────────────────────
def build_yearly_data(saved_kwh, feed_in_kwh, feed_in_tariff,
                      cost, e_price, e_inc, etf_ret, years):
    rows = []
    pv_cum = 0.0
    for y in range(1, years + 1):
        price = e_price * (1 + e_inc) ** (y - 1)
        pv_cum += saved_kwh * price + feed_in_kwh * feed_in_tariff
        pv_net = pv_cum - cost
        etf_val = cost * (1 + etf_ret) ** y
        etf_net = etf_val - cost
        rows.append({
            "Jahr": y,
            "PV kumuliert (€)": pv_cum,
            "PV netto (€)": pv_net,
            "ETF Wert (€)": etf_val,
            "ETF netto (€)": etf_net,
            "PV − ETF (€)": pv_net - etf_net,
        })
    return pd.DataFrame(rows)


def find_breakeven(df, col):
    pos = df[df[col] >= 0]
    return int(pos.iloc[0]["Jahr"]) if len(pos) > 0 else None


def calc_amortization_with_price_increase(invest: float, d_kwh: float, d_feed_in: float,
                                          e_price: float, e_inc: float, feed_in_tariff: float,
                                          max_years: int = 50) -> float:
    """
    Berechnet die Amortisation unter Berücksichtigung steigender Strompreise.
    Gibt die Anzahl der Jahre zurück, bis die kumulierte Ersparnis die Investition übersteigt.
    """
    if d_kwh <= 0 and d_feed_in <= 0:
        return float("inf")
    cumulative = 0.0
    for y in range(1, max_years + 1):
        price = e_price * (1 + e_inc) ** (y - 1)
        yearly_savings = d_kwh * price + d_feed_in * feed_in_tariff
        cumulative += yearly_savings
        if cumulative >= invest:
            # Interpolate within the year for more precision
            prev_cumulative = cumulative - yearly_savings
            remaining = invest - prev_cumulative
            fraction = remaining / yearly_savings if yearly_savings > 0 else 0
            return y - 1 + fraction
    return float("inf")


# ─── Styling helpers ────────────────────────────────────────────
def color_pos_neg(val):
    if not isinstance(val, (int, float)):
        return ""
    return "color: #4caf50" if val >= 0 else "color: #e53935"


def color_amort(val):
    if not isinstance(val, (int, float)):
        return ""
    if val <= 5:
        return "color: #4caf50"
    if val <= 10:
        return "color: #ff9800"
    return "color: #e53935"


def color_rendite(val):
    if not isinstance(val, (int, float)):
        return ""
    if val >= 15:
        return "color: #4caf50"
    if val >= 8:
        return "color: #ff9800"
    return "color: #e53935"


def color_autarkie(val):
    """Green ≥50%, orange ≥30%, red <30%."""
    if not isinstance(val, (int, float)):
        return ""
    if val >= 50:
        return "color: #4caf50"
    if val >= 30:
        return "color: #ff9800"
    return "color: #e53935"


def color_eigenverbrauch(val):
    """Green ≥70%, orange ≥50%, red <50%."""
    if not isinstance(val, (int, float)):
        return ""
    if val >= 70:
        return "color: #4caf50"
    if val >= 50:
        return "color: #ff9800"
    return "color: #e53935"


# ─── German number formatting ───────────────────────────────────
def de(val, decimals=0, sign=False):
    """Format a number with German locale (. = thousands, , = decimal)."""
    if not isinstance(val, (int, float)):
        return str(val)
    s = f"{val:{'+' if sign else ''},.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def de_styler(decimals=0, sign=False):
    """Return a callable for use in pandas Styler .format()."""
    return lambda v: de(v, decimals, sign)


# ═══════════════════════════════════════════════════════════════
#  SIDEBAR – Expanders
# ═══════════════════════════════════════════════════════════════

if "_active_base" not in st.session_state:
    st.session_state._active_base = list(PROFILE_BASE)
if "_flex_delta" not in st.session_state:
    st.session_state._flex_delta = list(FLEX_DELTA_DEFAULT)
if "_periodic_delta" not in st.session_state:
    st.session_state._periodic_delta = list(PERIODIC_DELTA_DEFAULT)

# Persist widget values when expanders are collapsed.
# Streamlit removes widget keys from session state when widgets aren't rendered.
# We mirror them to backup keys that survive across reruns.
_PERSISTED_KEYS = [
    "cfg_lat", "cfg_lon", "cfg_profile_mode", "cfg_annual_kwh",
    "cfg_flex_enabled", "cfg_flex_min_yield", "cfg_flex_pool", "cfg_flex_refresh",
    "cfg_periodic_enabled", "cfg_periodic_days",
    "cfg_seasonal_enabled", "cfg_season_winter", "cfg_season_summer",
    "cfg_year", "cfg_loss", "cfg_inverter_limit_enabled", "cfg_inverter_limit_w",
    "cfg_feed_in_tariff", "cfg_base_cost", "cfg_dc_coupled", "cfg_inverter_eff",
    "cfg_batt_loss", "cfg_min_soc_s", "cfg_max_soc_s", "cfg_min_soc_w", "cfg_max_soc_w",
    "cfg_e_price", "cfg_e_inc", "cfg_etf_ret", "cfg_years",
]
for _k in _PERSISTED_KEYS:
    _bk = f"_bak_{_k}"
    if _k in st.session_state:
        st.session_state[_bk] = st.session_state[_k]
    elif _bk in st.session_state:
        st.session_state[_k] = st.session_state[_bk]

st.sidebar.header("⚙️ Parameter")


def sv(key, default):
    """Read a value from session state with a fallback default."""
    return st.session_state.get(key, default)


def widget_value(key, default):
    """Return dict with 'value' only if key not already in session state.
    
    This prevents 'widget created with default value but also had value set via Session State API' errors
    when values are restored from deep links or other session state manipulations.
    """
    if key in st.session_state:
        return {}
    return {"value": default}


# --- Section 0: Standort & Daten ---
with st.sidebar.expander("📍 Standort", expanded=True):
    location_query = st.text_input(
        "🔍 Ort suchen", value="", key="cfg_location_query",
        placeholder="z. B. München, Berlin …",
        help="Sucht Koordinaten via OpenStreetMap. Du kannst die Werte unten auch manuell anpassen.",
    )
    if location_query:
        result = geocode(location_query)
        if result:
            display_name, found_lat, found_lon = result
            # Store the location name for display below the coordinate fields
            st.session_state._location_display_name = display_name
            if "cfg_lat" not in st.session_state or st.session_state.get("_last_geo_query") != location_query:
                st.session_state.cfg_lat = found_lat
                st.session_state.cfg_lon = found_lon
                st.session_state._last_geo_query = location_query
                st.rerun()
        else:
            st.warning("Ort nicht gefunden.")
            st.session_state._location_display_name = None

    # Initialize defaults in session state if not present (avoids value/key conflict)
    if "cfg_lat" not in st.session_state:
        st.session_state.cfg_lat = None
    if "cfg_lon" not in st.session_state:
        st.session_state.cfg_lon = None

    st.number_input("Breitengrad", format="%.4f", key="cfg_lat",
                    placeholder="z. B. 48.1371")
    st.number_input("Längengrad", format="%.4f", key="cfg_lon",
                    placeholder="z. B. 11.5754")

    # Show location name below coordinate fields (from search or reverse geocoding)
    _lat, _lon = sv("cfg_lat", None), sv("cfg_lon", None)
    if _lat is not None and _lon is not None:
        # If no search query, use reverse geocoding to get location name
        if not location_query:
            _coord_key = f"{_lat:.4f},{_lon:.4f}"
            if st.session_state.get("_reverse_geo_key") != _coord_key:
                _place_name = reverse_geocode(_lat, _lon)
                st.session_state._reverse_geo_key = _coord_key
                st.session_state._location_display_name = _place_name
        # Display the location name
        _place_name = st.session_state.get("_location_display_name")
        if _place_name:
            st.caption(f"📍 {_place_name}")

# --- Section 1: Verbrauch ---
with st.sidebar.expander("💡 Verbrauch"):
    _profile_modes = ["Einfach", "Erweitert"]
    st.radio(
        "Lastprofil-Modus", _profile_modes, horizontal=True,
        index=_profile_modes.index(sv("cfg_profile_mode", "Einfach")),
        key="cfg_profile_mode",
        help="**Einfach**: Standard-Lastprofil (BDEW H0) wird auf deinen Jahresverbrauch skaliert. "
             "**Erweitert**: Eigenes stündliches Lastprofil (Watt) für einen typischen Tag.",
    )
    if sv("cfg_profile_mode", "Einfach") == "Einfach":
        st.number_input(
            "Jahresverbrauch (kWh)", value=sv("cfg_annual_kwh", None), step=100,
            min_value=100, key="cfg_annual_kwh",
            placeholder="z. B. 3000",
            help="Das Standard-Lastprofil wird auf deinen Jahresverbrauch skaliert. "
                 "Der Gesamtverbrauch im Report kann aufgrund der weiteren Einstellungen sowie Rundungsfehlern "
                 "geringfügig davon abweichen.",
        )
        annual_kwh = sv("cfg_annual_kwh", None)
        if annual_kwh is not None:
            scale = annual_kwh / _DEFAULT_ANNUAL_KWH
            st.session_state._active_base = [round(w * scale) for w in PROFILE_BASE]
    else:
        st.caption("Verbrauch in Watt für jede Stunde eines typischen Tages")
        profile_df = pd.DataFrame({
            "Stunde": [f"{h:02d}:00" for h in range(24)],
            "Verbrauch (W)": st.session_state._active_base,
        })
        edited_df = st.data_editor(
            profile_df, disabled=["Stunde"], hide_index=True,
            use_container_width=True, key="profile_editor",
        )
        # Update session state from editor (compare to avoid unnecessary updates)
        new_values = edited_df["Verbrauch (W)"].tolist()
        if new_values != st.session_state._active_base:
            st.session_state._active_base = new_values
            st.rerun()

    st.toggle("❄️ Saisonale Skalierung", key="cfg_seasonal_enabled",
        help="Verbrauch im Winter höher (Beleuchtung, Heizung), im Sommer niedriger. "
             "Basiert auf dem BDEW H0 Standardlastprofil.",
        **widget_value("cfg_seasonal_enabled", True))
    if sv("cfg_seasonal_enabled", True):
        st.slider("Winter-Faktor (%)", 100, 130, key="cfg_season_winter",
            help="Nov–Mär: Mehr Verbrauch durch Beleuchtung, Heizungspumpen, mehr Zeit drinnen.",
            **widget_value("cfg_season_winter", 114))
        st.slider("Sommer-Faktor (%)", 70, 100, key="cfg_season_summer",
            help="Mai–Sep: Weniger Verbrauch durch längere Tage, weniger Beleuchtung.",
            **widget_value("cfg_season_summer", 87))
        st.caption("Apr & Okt: 100% (Übergangszeit)")

    st.toggle(
        "☀️ Lastverschiebung an Sonnentagen", key="cfg_flex_enabled",
        help="Zusätzlicher Verbrauch **nur an ertragreichen Tagen** "
             "(z. B. 🧺 Waschmaschine, Spülmaschine). "
             "Wird nur ausgelöst, wenn genug PV-Ertrag erwartet wird.",
        **widget_value("cfg_flex_enabled", False))
    if sv("cfg_flex_enabled", False):
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
            **widget_value("cfg_flex_min_yield", 5.0))
        st.number_input(
            "Max. Einsätze im Vorrat", step=1, min_value=1,
            key="cfg_flex_pool",
            help="Wird aufgefüllt wenn nicht ausgelöst, max. dieses Limit. "
                 "Beispiel Waschmaschine: wie viele Maschinen max. hintereinander, bis keine Wäsche mehr da ist?",
            **widget_value("cfg_flex_pool", 3))
        st.number_input(
            "Auffrischungsrate (pro Tag)", step=0.1, min_value=0.0,
            format="%.1f", key="cfg_flex_refresh",
            help="Einsätze die pro Nicht-Flex-Tag zum Vorrat hinzugefügt werden. "
                 "Beispiel Waschmaschine: wie lange dauert es, bis ein neuer Waschgang durchgeführt werden kann "
                 "(z.B. 0,5 entspricht 2 Tage)?",
            **widget_value("cfg_flex_refresh", 0.5))

    st.toggle(
        "🔄 Periodische Zusatzlast", key="cfg_periodic_enabled",
        help="Regelmäßiger Zusatzverbrauch **unabhängig vom Wetter** "
             "(z. B. 🌡️ Warmwasser-Desinfektion). "
             "Wird in festen Intervallen ausgelöst.",
        **widget_value("cfg_periodic_enabled", False))
    if sv("cfg_periodic_enabled", False):
        st.number_input(
            "Intervall (Tage)", step=1, min_value=1, key="cfg_periodic_days",
            **widget_value("cfg_periodic_days", 3))
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

# --- Section 2: PV-System ---
with st.sidebar.expander("⚡ PV-System"):
    _year_options = list(range(2005, 2021))  # PVGIS supports 2005-2020
    st.selectbox("PVGIS-Datenjahr", _year_options,
                 index=_year_options.index(sv("cfg_year", 2020)), key="cfg_year")
    st.slider("WR-Wirkungsgrad (%)", 80, 100, key="cfg_inverter_eff",
              help="Wirkungsgrad des Wechselrichters. Wird auf die AC-Ausgabe angewendet, "
                   "inkl. Batterie-Entladung bei DC-gekoppelten Systemen.",
              **widget_value("cfg_inverter_eff", 96))
    st.slider("Sonstige PV-Verluste (%)", 0, 20, key="cfg_loss",
              help="Verluste durch Kabel, Verschmutzung, Temperatur, Mismatch etc. "
                   "**Ohne Wechselrichterverluste**, diese werden anhand des Wirkungsgrades (s.o.) berechnet.",
              **widget_value("cfg_loss", 5))
    st.toggle(
        "⚡ Wechselrichter-Limit", key="cfg_inverter_limit_enabled",
        help="Begrenzt die maximale Einspeiseleistung des Wechselrichters. "
             "Deaktivieren für größere PV-Anlagen ohne Begrenzung.",
        **widget_value("cfg_inverter_limit_enabled", True))
    if sv("cfg_inverter_limit_enabled", True):
        st.number_input(
            "Wechselrichter-Limit (W)", step=100, min_value=100,
            key="cfg_inverter_limit_w",
            help="Maximale AC-Ausgangsleistung des Wechselrichters in Watt.",
            **widget_value("cfg_inverter_limit_w", 800))
    st.number_input(
        "Einspeisevergütung (ct/kWh)", step=0.5, min_value=0.0,
        format="%.1f", key="cfg_feed_in_tariff",
        help="Vergütung für ins Netz eingespeisten Strom. "
             "In Deutschland aktuell ca. 8,0 ct/kWh für Anlagen bis 10 kWp. "
             "Bei Balkonkraftwerken in der Regel keine Vergütung aufgrund vereinfachter Anmeldung.",
        **widget_value("cfg_feed_in_tariff", 0.0))
    st.number_input("Kosten PV-System ohne Speicher (€)", step=50, key="cfg_base_cost",
                    **widget_value("cfg_base_cost", 800))
    st.divider()
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

# --- Section 3: Speicher ---
with st.sidebar.expander("🔋 Speicher"):
    _coupling_options = ["DC-gekoppelt", "AC-gekoppelt"]
    st.radio(
        "Speicheranbindung", _coupling_options, horizontal=True,
        index=_coupling_options.index(sv("cfg_dc_coupled", "DC-gekoppelt")),
        key="cfg_dc_coupled",
        help="**DC-gekoppelt**: Batterie lädt ohne Limit direkt von den Panels - "
             "Wechselrichter-Limit gilt nur für die AC-Seite. "
             "**AC-gekoppelt**: Batterie lädt mit Limit von AC – "
             "Wechselrichter-Limit begrenzt den gesamten PV-Ertrag.",
    )
    st.slider("Lade-/Entladeverluste (%)", 0, 30, key="cfg_batt_loss",
              help="Verlust pro Richtung (Laden und Entladen). "
                   "Bei 10% ergibt sich ein Roundtrip-Wirkungsgrad von ~81% (19% Gesamtverlust). "
                   "Typisch: 5% für gute LiFePO4, 10% für günstigere Speicher.",
              **widget_value("cfg_batt_loss", 10))
    st.slider("Min. Ladezustand Sommer (%)", 0, 100, key="cfg_min_soc_s",
              **widget_value("cfg_min_soc_s", 10))
    st.slider("Max. Ladezustand Sommer (%)", 0, 100, key="cfg_max_soc_s",
              **widget_value("cfg_max_soc_s", 100))
    st.slider("Min. Ladezustand Winter (%)", 0, 100, key="cfg_min_soc_w",
              **widget_value("cfg_min_soc_w", 20))
    st.slider("Max. Ladezustand Winter (%)", 0, 100, key="cfg_max_soc_w",
              **widget_value("cfg_max_soc_w", 100))
    st.divider()
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

# --- Section 4: Preise & Vergleich ---
with st.sidebar.expander("💰 Preise & Vergleich"):
    st.number_input("Strompreis (€/kWh)", step=0.01, format="%.2f", key="cfg_e_price",
                    **widget_value("cfg_e_price", 0.27))
    st.number_input(
        "Strompreis-Steigerung (%/a)", step=0.5, format="%.1f", key="cfg_e_inc",
        **widget_value("cfg_e_inc", 3.0))
    st.number_input(
        "ETF-Rendite (%/a)", step=0.5, format="%.1f", key="cfg_etf_ret",
        **widget_value("cfg_etf_ret", 7.0))
    st.slider("Analyse-Horizont (Jahre)", 5, 30, key="cfg_years",
              **widget_value("cfg_years", 15))

# ═══════════════════════════════════════════════════════════════
#  READ ALL CONFIG FROM SESSION STATE
# ═══════════════════════════════════════════════════════════════
lat = sv("cfg_lat", None)
lon = sv("cfg_lon", None)
data_year = sv("cfg_year", 2020)
system_loss = sv("cfg_loss", 5)  # Non-inverter losses only (cables, soiling, temperature)
inverter_limit_enabled = sv("cfg_inverter_limit_enabled", True)
inverter_limit_w = sv("cfg_inverter_limit_w", 800) if inverter_limit_enabled else None
feed_in_tariff = sv("cfg_feed_in_tariff", 0.0) / 100  # ct → €
dc_coupled = sv("cfg_dc_coupled", "DC-gekoppelt") == "DC-gekoppelt"

batt_loss = sv("cfg_batt_loss", 10)
inverter_eff = sv("cfg_inverter_eff", 96)
min_soc_summer = sv("cfg_min_soc_s", 10)
max_soc_summer = sv("cfg_max_soc_s", 100)
min_soc_winter = sv("cfg_min_soc_w", 20)
max_soc_winter = sv("cfg_max_soc_w", 100)
base_cost = sv("cfg_base_cost", 800)

active_base = st.session_state._active_base
flex_enabled = sv("cfg_flex_enabled", False)
flex_delta = st.session_state._flex_delta if flex_enabled else [0] * 24
flex_min_yield = sv("cfg_flex_min_yield", 5.0)
flex_pool = sv("cfg_flex_pool", 3)
flex_refresh = sv("cfg_flex_refresh", 0.5)

periodic_enabled = sv("cfg_periodic_enabled", False)
periodic_delta = st.session_state._periodic_delta if periodic_enabled else [0] * 24
periodic_days = sv("cfg_periodic_days", 3)

seasonal_enabled = sv("cfg_seasonal_enabled", True)
season_winter = sv("cfg_season_winter", 114)
season_summer = sv("cfg_season_summer", 87)

e_price = sv("cfg_e_price", 0.27)
e_inc = sv("cfg_e_inc", 1.0) / 100
etf_ret = sv("cfg_etf_ret", 7.0) / 100
analysis_years = sv("cfg_years", 15)

modules = st.session_state.modules
storages = st.session_state.storages

# ═══════════════════════════════════════════════════════════════
#  VALIDATE REQUIRED CONFIGURATION
# ═══════════════════════════════════════════════════════════════
profile_mode = sv("cfg_profile_mode", "Einfach")
missing = []
if lat is None or lon is None:
    missing.append("📍 **Standort** – Breitengrad und Längengrad eingeben oder Ort suchen")
if profile_mode == "Einfach" and sv("cfg_annual_kwh", None) is None:
    missing.append("💡 **Jahresverbrauch** – jährlichen Stromverbrauch in kWh angeben")

if missing:
    st.title("☀️ PV-Analyse mit Speichervergleich")
    st.info(
        "Bitte konfiguriere mindestens folgende Parameter in der **Seitenleiste** (⚙️), "
        "um die Analyse zu starten:"
    )
    for m in missing:
        st.markdown(f"- {m}")

    st.markdown("Nach Hinzufügen der erforderlichen Parameter wird ein Report mit Standardwerten generiert. "
                "Dieser verwendet Beispielwerte für ein 2kWp PV-System mit drei unterschiedlichen Speicherkonfigurationen.")
    st.markdown("Du kannst dann nach und nach weitere Einstellungen anpassen und die Auswirkungen direkt sehen.")
    st.divider()
    st.caption(
        "💡 Tipp: Öffne die Abschnitte in der Seitenleiste links, um Standort und "
        "Verbrauchsdaten einzugeben. Die Analyse wird automatisch gestartet, "
        "sobald alle Pflichtfelder ausgefüllt sind."
    )
    st.stop()

# ═══════════════════════════════════════════════════════════════
#  COMPUTE
# ═══════════════════════════════════════════════════════════════

# Fetch PV data for each module and sum
with st.spinner("Lade PV-Ertragsdaten von PVGIS …"):
    try:
        pv_arrays = []
        for mod in modules:
            arr = get_pvgis_hourly(
                lat, lon, mod["peak"], mod["slope"], mod["azi"],
                system_loss, data_year,
            )
            pv_arrays.append(arr)
        pv_total = sum(pv_arrays)
    except Exception as exc:
        st.error(f"Fehler beim Laden der PVGIS-Daten: {exc}")
        st.stop()

pv_gen_total = float(np.sum(pv_total))

# Build scenario list: base (no storage) + each storage option sorted by capacity
sorted_storages = sorted(storages, key=lambda s: s["cap"])
scenarios = [("Ohne Speicher", 0.0, base_cost)]
for s in sorted_storages:
    scenarios.append((f"{s['name']} ({s['cap']:.2f} kWh)", s["cap"], base_cost + s["cost"]))

# Run simulations
sim_kwargs = dict(
    batt_loss_pct=batt_loss, data_year=data_year,
    inverter_limit_kw=inverter_limit_w / 1000 if inverter_limit_w is not None else None,
    dc_coupled=dc_coupled,
    inverter_eff_pct=inverter_eff,
    min_soc_summer_pct=min_soc_summer, min_soc_winter_pct=min_soc_winter,
    max_soc_summer_pct=max_soc_summer, max_soc_winter_pct=max_soc_winter,
    flex_load_enabled=flex_enabled, flex_min_yield=flex_min_yield,
    flex_pool_size=flex_pool,
    flex_delta=flex_delta, flex_refresh_rate=flex_refresh,
    periodic_load_enabled=periodic_enabled, periodic_delta=periodic_delta,
    periodic_interval_days=periodic_days,
    profile_base=active_base,
    seasonal_enabled=seasonal_enabled,
    season_winter_pct=season_winter,
    season_summer_pct=season_summer,
)

results = []
for name, cap, cost in scenarios:
    grid_imp, total_cons, fi, curt, monthly = simulate(pv_total, cap, **sim_kwargs)
    self_consumed = pv_gen_total - fi - curt
    results.append({
        "name": name, "cap": cap, "cost": cost,
        "grid_import": grid_imp, "total_consumption": total_cons,
        "autarkie": (1 - grid_imp / total_cons) * 100,
        "feed_in": fi,
        "curtailed": curt,
        "eigenverbrauch": (self_consumed / pv_gen_total * 100) if pv_gen_total > 0 else 0,
        "monthly": monthly,
    })

total_cons = results[0]["total_consumption"]
pv_gen = pv_gen_total

# ═══════════════════════════════════════════════════════════════
#  DISPLAY
# ═══════════════════════════════════════════════════════════════
st.title("☀️ PV-Analyse mit Speichervergleich")
place_name = reverse_geocode(lat, lon)
location_str = f"{place_name} ({lat}°N / {lon}°E)" if place_name else f"{lat}°N / {lon}°E"
st.caption(f"PVGIS-Stundenwerte {data_year}  ·  Standort {location_str}")

subtitle_parts = []
if inverter_limit_w is not None:
    coupling = "DC" if dc_coupled else "AC"
    subtitle_parts.append(f"WR-Limit {inverter_limit_w} W ({coupling}-gekoppelt)")
if feed_in_tariff > 0:
    subtitle_parts.append(f"Einspeisevergütung {de(feed_in_tariff * 100, 1)} ct/kWh")
st.caption(" · ".join(subtitle_parts))

total_peak_kwp = sum(m["peak"] for m in modules)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Gesamtverbrauch", f"{de(total_cons)} kWh/a")
col2.metric("Stromkosten ohne PV", f"{de(total_cons * e_price)} €/a")
col3.metric("PV-Leistung", f"{de(total_peak_kwp, 1)} kWp")
col4.metric("PV-Erzeugung", f"{de(pv_gen)} kWh/a")

# ─── Szenario-Übersicht ────────────────────────────────────────
st.header("📊 Szenario-Übersicht")
overview_rows = []
for r in results:
    saved = total_cons - r["grid_import"]
    feed_rev = r["feed_in"] * feed_in_tariff
    row = {
        "Szenario": r["name"],
        "Speicher (kWh)": de(r['cap'], 2),
        "Investition (€)": r["cost"],
        "Netzbezug (kWh/a)": round(r["grid_import"]),
        "Einspeisung (kWh/a)": round(r["feed_in"]),
        "Eingespart (kWh/a)": round(saved),
        "Autarkie (%)": round(r["autarkie"], 1),
        "Eigenverbr. (%)": round(r["eigenverbrauch"], 1),
    }
    if feed_in_tariff > 0:
        row["Vergütung (€/a)"] = round(feed_rev, 2)
    row["Ersparnis (€/a)"] = round(saved * e_price + feed_rev, 2)
    overview_rows.append(row)

overview_fmt = {
    "Autarkie (%)": de_styler(1),
    "Eigenverbr. (%)": de_styler(1),
    "Ersparnis (€/a)": de_styler(2),
}
if feed_in_tariff > 0:
    overview_fmt["Vergütung (€/a)"] = de_styler(2)
st.dataframe(
    pd.DataFrame(overview_rows).style
    .format(overview_fmt)
    .map(color_autarkie, subset=["Autarkie (%)"])
    .map(color_eigenverbrauch, subset=["Eigenverbr. (%)"]),
    use_container_width=True, hide_index=True,
)

st.caption(f"📌 Die Ersparnis (€/a) bezieht sich auf das 1. Jahr. Durch steigende Strompreise "
           f"(+{e_inc * 100:.0f} %/a) ist die tatsächliche Ersparnis in späteren Jahren höher.")

# ─── Monatliche Energiebilanz ───────────────────────────────────
MONTH_LABELS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

st.header("⚡ Monatliche Energiebilanz")
st.caption("Woher kommt der Strom? Verbrauchsdeckung nach Quelle pro Monat.")

# Compute shared Y-axis range across all scenarios for consistent scale
y_max_all = 0.0
y_min_all = 0.0
for r in results:
    for m in range(1, 13):
        d = r["monthly"][m]
        positive = d["Direkt-PV"] + d["Batterie"] + d["Netzbezug"]
        negative = -d["Einspeisung"]
        y_max_all = max(y_max_all, positive)
        y_min_all = min(y_min_all, negative)
# Add 5% padding
y_max_all *= 1.05
y_min_all *= 1.05

energy_tabs = st.tabs([r["name"] for r in results])
for etab, r in zip(energy_tabs, results):
    with etab:
        monthly = r["monthly"]
        rows = []
        for m in range(1, 13):
            d = monthly[m]
            rows.append({
                "Monat": MONTH_LABELS[m - 1],
                "Monat_Nr": m,
                "Direkt-PV": d["Direkt-PV"],
                "Batterie": d["Batterie"],
                "Netzbezug": d["Netzbezug"],
                "Einspeisung": -d["Einspeisung"],  # negative for export
            })
        mdf = pd.DataFrame(rows)

        # Melt for Altair stacked bar
        melted = mdf.melt(
            id_vars=["Monat", "Monat_Nr"],
            value_vars=["Direkt-PV", "Batterie", "Netzbezug", "Einspeisung"],
            var_name="Quelle", value_name="kWh",
        )

        bars = (
            alt.Chart(melted)
            .mark_bar()
            .encode(
                x=alt.X("Monat:N", sort=MONTH_LABELS, title=None),
                y=alt.Y("kWh:Q", title="kWh", scale=alt.Scale(domain=[y_min_all, y_max_all])),
                color=alt.Color(
                    "Quelle:N",
                    scale=alt.Scale(
                        domain=["Direkt-PV", "Batterie", "Netzbezug", "Einspeisung"],
                        range=["#ff9800", "#4db68a", "#488fc2", "#a280db"],
                    ),
                    title="Quelle",
                ),
                order=alt.Order("order:Q"),
                tooltip=[
                    alt.Tooltip("Monat:N"),
                    alt.Tooltip("Quelle:N"),
                    alt.Tooltip("kWh:Q", format=",.0f"),
                ],
            )
            .transform_calculate(
                order="datum.Quelle === 'Direkt-PV' ? 0 : datum.Quelle === 'Batterie' ? 1 "
                      ": datum.Quelle === 'Netzbezug' ? 2 : 3"
            )
            .properties(height=320)
        )

        # Zero line
        zero = (
            alt.Chart(pd.DataFrame({"y": [0]}))
            .mark_rule(color="gray", strokeWidth=1)
            .encode(y="y:Q")
        )

        # Consumption line overlay
        cons_df = pd.DataFrame([
            {"Monat": MONTH_LABELS[m - 1], "Verbrauch": monthly[m]["Verbrauch"]}
            for m in range(1, 13)
        ])
        line = (
            alt.Chart(cons_df)
            .mark_line(color="#78909c", strokeWidth=2, strokeDash=[6, 3])
            .encode(
                x=alt.X("Monat:N", sort=MONTH_LABELS),
                y=alt.Y("Verbrauch:Q"),
                tooltip=[
                    alt.Tooltip("Monat:N"),
                    alt.Tooltip("Verbrauch:Q", title="Verbrauch (kWh)", format=",.0f"),
                ],
            )
        )
        points = (
            alt.Chart(cons_df)
            .mark_point(color="#78909c", size=30, filled=True)
            .encode(
                x=alt.X("Monat:N", sort=MONTH_LABELS),
                y=alt.Y("Verbrauch:Q"),
            )
        )

        st.altair_chart(
            (bars + zero + line + points).configure(
                locale={
                    "number": {
                        "decimal": ",", "thousands": ".", "grouping": [3],
                        "currency": ["", " €"],
                    }
                }
            ),
            use_container_width=True,
        )
        st.caption("📊 Balken = Verbrauchsdeckung (☀️ Direkt-PV, 🔋 Batterie, 🔵 Netzbezug) · "
                   "🟣 Einspeisung (negativ) · Gestrichelte Linie = Gesamtverbrauch")

# ─── Inkrementelle Analyse ─────────────────────────────────────
if len(results) > 1:
    st.header("🔋 Inkrementelle Analyse")
    st.caption("Mehrwert jeder Ausbaustufe gegenüber der vorherigen. Die Amortisation und Rendite werden individuell "
               "pro Upgrade berechnet: wie lange dauert es, bis der zusätzliche Speicher sich selbst "
               "amortisiert hat?")
    incr_rows = []
    for i in range(1, len(results)):
        prev, curr = results[i - 1], results[i]
        d_cost = curr["cost"] - prev["cost"]
        d_kwh = prev["grid_import"] - curr["grid_import"]
        d_feed_in = curr["feed_in"] - prev["feed_in"]  # typically negative (more storage → less export)
        d_eur = d_kwh * e_price + d_feed_in * feed_in_tariff  # Year 1 savings
        rend = (d_eur / d_cost) * 100 if d_cost > 0 else 0
        amort = calc_amortization_with_price_increase(
            d_cost, d_kwh, d_feed_in, e_price, e_inc, feed_in_tariff
        )
        incr_rows.append({
            "Upgrade": f"{prev['name']}  →  {curr['name']}",
            "Δ Invest (€)": d_cost,
            "Δ Ersparnis (kWh/a)": round(d_kwh),
            "Δ Ersparnis (€/a)": d_eur,
            "Rendite (%/a)": rend,
            "Amortisation (a)": amort,
        })
    incr_df = pd.DataFrame(incr_rows)
    styled_incr = (
        incr_df.style
        .format({
            "Δ Invest (€)": de_styler(0),
            "Δ Ersparnis (kWh/a)": de_styler(1),
            "Δ Ersparnis (€/a)": de_styler(2),
            "Rendite (%/a)": de_styler(2),
            "Amortisation (a)": de_styler(1),
        })
        .map(color_pos_neg, subset=["Δ Ersparnis (€/a)"])
        .map(color_rendite, subset=["Rendite (%/a)"])
        .map(color_amort, subset=["Amortisation (a)"])
    )
    st.dataframe(styled_incr, use_container_width=True, hide_index=True)
    st.caption(f"📌 Die Ersparnis (€/a) und Rendite (%/a) beziehen sich auf das 1. Jahr. Durch steigende Strompreise "
               f"(+{e_inc * 100:.0f} %/a) ist die tatsächliche Ersparnis in späteren Jahren höher. "
               f"Die Amortisation berücksichtigt dies korrekt.")

# ─── Langzeit-Chart: PV vs ETF ─────────────────────────────────
st.header(f"📈 Langzeit-Vergleich: PV vs. ETF ({analysis_years} Jahre)")
assumptions = f"Annahmen: Strompreis +{e_inc * 100:.0f} %/a · ETF +{etf_ret * 100:.0f} %/a"
if feed_in_tariff > 0:
    assumptions += f" · Einspeisevergütung {de(feed_in_tariff * 100, 1)} ct/kWh (konstant)"
st.caption(assumptions)

chart_frames = []
for r in results:
    saved_kwh = total_cons - r["grid_import"]
    df = build_yearly_data(saved_kwh, r["feed_in"], feed_in_tariff,
                           r["cost"], e_price, e_inc, etf_ret, analysis_years)
    df["Szenario"] = r["name"]
    chart_frames.append(df)
all_data = pd.concat(chart_frames, ignore_index=True)

pv_line = all_data[["Jahr", "PV netto (€)", "Szenario"]].rename(columns={"PV netto (€)": "Wert"})
pv_line["Anlage"] = "PV: " + pv_line["Szenario"]
pv_line["Art"] = "PV"

etf_line = all_data[["Jahr", "ETF netto (€)", "Szenario"]].rename(columns={"ETF netto (€)": "Wert"})
etf_line["Anlage"] = "ETF: " + etf_line["Szenario"]
etf_line["Art"] = "ETF"

chart_df = pd.concat([pv_line, etf_line], ignore_index=True)

chart = (
    alt.Chart(chart_df)
    .mark_line(strokeWidth=2)
    .encode(
        x=alt.X("Jahr:Q", title="Jahr", axis=alt.Axis(format="d")),
        y=alt.Y("Wert:Q", title="Netto-Gewinn (€)", axis=alt.Axis(format=",.0f")),
        color=alt.Color("Anlage:N", title="Anlage"),
        strokeDash=alt.StrokeDash(
            "Art:N",
            scale=alt.Scale(domain=["PV", "ETF"], range=[[0], [6, 4]]),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("Anlage:N"),
            alt.Tooltip("Jahr:Q", format="d"),
            alt.Tooltip("Wert:Q", title="€", format="+,.0f"),
        ],
    )
    .properties(height=420)
    .interactive()
)
zero_rule = (
    alt.Chart(pd.DataFrame({"y": [0]}))
    .mark_rule(strokeDash=[4, 4], color="gray")
    .encode(y="y:Q")
)
st.altair_chart(
    (chart + zero_rule).configure(
        locale={
            "number": {
                "decimal": ",",
                "thousands": ".",
                "grouping": [3],
                "currency": ["", " €"],
            }
        }
    ),
    use_container_width=True,
)

# ─── Per-scenario detail tables ─────────────────────────────────
tabs = st.tabs([r["name"] for r in results])
for tab, r in zip(tabs, results):
    with tab:
        saved_kwh = total_cons - r["grid_import"]
        df = build_yearly_data(saved_kwh, r["feed_in"], feed_in_tariff,
                               r["cost"], e_price, e_inc, etf_ret, analysis_years)

        be_pv = find_breakeven(df, "PV netto (€)")
        be_etf = find_breakeven(df, "PV − ETF (€)")

        c1, c2, c3 = st.columns(3)
        c1.metric("Amortisation", f"{be_pv} Jahre" if be_pv else "nie")
        c2.metric("PV schlägt ETF nach", f"{be_etf} Jahren" if be_etf else "nie")
        final = df.iloc[-1]
        c3.metric(
            f"Δ PV − ETF nach {analysis_years}a",
            f"{de(final['PV − ETF (€)'], sign=True)} €",
        )

        euro_cols = [c for c in df.columns if "(€)" in c]
        fmt = {c: de_styler(0, sign=True) for c in euro_cols}
        fmt["Jahr"] = de_styler(0)
        styled_detail = (
            df.style
            .format(fmt)
            .map(color_pos_neg, subset=["PV netto (€)", "PV − ETF (€)"])
        )
        st.dataframe(styled_detail, use_container_width=True, hide_index=True)

# ─── Zusammenfassung ────────────────────────────────────────────
st.header("🏆 Zusammenfassung")

summary_rows = []
for r in results:
    saved_kwh = total_cons - r["grid_import"]
    pv_savings = sum(
        saved_kwh * e_price * (1 + e_inc) ** y + r["feed_in"] * feed_in_tariff
        for y in range(analysis_years)
    )
    pv_profit = pv_savings - r["cost"]
    etf_profit = r["cost"] * (1 + etf_ret) ** analysis_years - r["cost"]
    summary_rows.append({
        "Szenario": r["name"],
        "Investition (€)": r["cost"],
        "PV Gewinn (€)": round(pv_profit, 2),
        "ETF Gewinn (€)": round(etf_profit, 2),
        "Besser": "PV" if pv_profit > etf_profit else "ETF",
        "Differenz (€)": round(pv_profit - etf_profit, 2),
    })

summary_df = pd.DataFrame(summary_rows)
styled_summary = (
    summary_df.style
    .format({
        "Investition (€)": de_styler(0),
        "PV Gewinn (€)": de_styler(0, sign=True),
        "ETF Gewinn (€)": de_styler(0, sign=True),
        "Differenz (€)": de_styler(0, sign=True),
    })
    .map(color_pos_neg, subset=["PV Gewinn (€)", "ETF Gewinn (€)", "Differenz (€)"])
)
st.dataframe(styled_summary, use_container_width=True, hide_index=True)

best = max(summary_rows, key=lambda r: r["PV Gewinn (€)"])
st.success(
    f"**{best['Szenario']}** erzielt den höchsten absoluten Gewinn nach "
    f"{analysis_years} Jahren: **{de(best['PV Gewinn (€)'], sign=True)} €**"
)

# ─── Sharing ────────────────────────────────────────────────────
st.divider()
if st.button("🔗 Link mit aktueller Konfiguration erstellen"):
    try:
        encoded = encode_config()
        base_url = st.context.headers.get("Origin", "")
        share_url = f"{base_url}/?cfg={encoded}"
        st.code(share_url, language=None)
        st.caption("Link kopieren und teilen – alle Parameter sind im Link gespeichert.")
    except Exception as exc:
        st.error(f"Fehler beim Erstellen des Links: {exc}")
