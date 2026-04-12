"""
External API integrations for the PV analysis application.
Handles PVGIS data fetching and geocoding via OpenStreetMap.
"""
from __future__ import annotations

import time
from typing import TypeVar

import numpy as np
import requests
import streamlit as st

from solarbatteryield.utils import get_secret


# Nominatim contact email (recommended by usage policy to avoid blocks)
# https://operations.osmfoundation.org/policies/nominatim/
NOMINATIM_EMAIL = get_secret("NOMINATIM_EMAIL", "")

# Geocoding is disabled by default for local development to avoid rate limiting.
# Set NOMINATIM_ENABLED=true to enable (requires NOMINATIM_EMAIL to be set).
NOMINATIM_ENABLED = get_secret("NOMINATIM_ENABLED", "").lower() in ("true", "1", "yes")


# ─── Custom Exceptions ─────────────────────────────────────────
class PVAnalysisError(Exception):
    """Base exception for PV Analysis application."""
    pass


class APIError(PVAnalysisError):
    """Exception raised when an external API call fails."""
    def __init__(self, service: str, message: str, status_code: int | None = None):
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service} Fehler: {message}")


class PVGISError(APIError):
    """Exception raised when PVGIS API call fails."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__("PVGIS", message, status_code)


class GeocodingError(APIError):
    """Exception raised when geocoding fails."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__("Geocoding", message, status_code)


class ConfigurationError(PVAnalysisError):
    """Exception raised when configuration is invalid."""
    pass


def _check_nominatim_enabled() -> None:
    """
    Check if Nominatim geocoding is properly configured.
    
    Raises:
        GeocodingError: If geocoding is disabled or email is not configured.
    """
    if not NOMINATIM_ENABLED:
        raise GeocodingError(
            "Geocoding ist deaktiviert. Setze NOMINATIM_ENABLED=true um es zu aktivieren."
        )
    if not NOMINATIM_EMAIL:
        raise GeocodingError(
            "NOMINATIM_EMAIL muss gesetzt sein, wenn Geocoding aktiviert ist."
        )


# ─── Retry Logic ───────────────────────────────────────────────
T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor


def _retry_with_backoff(
    func,
    retry_config: RetryConfig = RetryConfig(),
    error_class: type[APIError] = APIError,
    service_name: str = "API"
):
    """
    Execute a function with exponential backoff retry logic.
    
    Args:
        func: Callable to execute (should return a requests.Response)
        retry_config: Retry configuration
        error_class: Exception class to raise on failure
        service_name: Name of the service for error messages
    
    Returns:
        The function's return value
    
    Raises:
        APIError subclass on persistent failure
    """
    last_exception = None
    
    for attempt in range(retry_config.max_retries):
        try:
            response = func()
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout as e:
            last_exception = e
            delay = min(
                retry_config.base_delay * (retry_config.backoff_factor ** attempt),
                retry_config.max_delay
            )
            if attempt < retry_config.max_retries - 1:
                time.sleep(delay)
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            delay = min(
                retry_config.base_delay * (retry_config.backoff_factor ** attempt),
                retry_config.max_delay
            )
            if attempt < retry_config.max_retries - 1:
                time.sleep(delay)
        except requests.exceptions.HTTPError as e:
            # Don't retry client errors (4xx)
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise error_class(
                    f"Anfrage fehlgeschlagen: {e.response.status_code}",
                    e.response.status_code
                )
            last_exception = e
            delay = min(
                retry_config.base_delay * (retry_config.backoff_factor ** attempt),
                retry_config.max_delay
            )
            if attempt < retry_config.max_retries - 1:
                time.sleep(delay)
    
    # All retries exhausted
    if isinstance(last_exception, requests.exceptions.Timeout):
        raise error_class(f"Zeitüberschreitung nach {retry_config.max_retries} Versuchen")
    elif isinstance(last_exception, requests.exceptions.ConnectionError):
        raise error_class(f"Verbindungsfehler – bitte Internetverbindung prüfen")
    else:
        raise error_class(f"Anfrage fehlgeschlagen nach {retry_config.max_retries} Versuchen")


# ─── API Functions ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_pvgis_hourly(
    lat: float, 
    lon: float, 
    peak: float, 
    slope: float, 
    azi: float, 
    loss: float, 
    year: int
) -> np.ndarray:
    """
    Fetch hourly PV generation data from PVGIS API.
    
    Args:
        lat: Latitude of the location
        lon: Longitude of the location
        peak: Peak power of the PV system in kWp
        slope: Tilt angle of the panels in degrees
        azi: Azimuth angle (0=South, 90=West, -90=East)
        loss: System losses in percent
        year: Reference year for solar irradiance data
        
    Returns:
        NumPy array of hourly generation values in kWh
        
    Raises:
        PVGISError: If the API request fails
    """
    url = (
        f"https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?"
        f"lat={lat}&lon={lon}&rrad=1&use_horizon=1&peakpower={peak}&"
        f"mountingplace=free&angle={slope}&aspect={azi}&"
        f"pvcalculation=1&loss={loss}&outputformat=json&"
        f"startyear={year}&endyear={year}"
    )
    
    retry_config = RetryConfig(max_retries=3, base_delay=2.0)
    
    try:
        response = _retry_with_backoff(
            lambda: requests.get(url, timeout=30),
            retry_config=retry_config,
            error_class=PVGISError,
            service_name="PVGIS"
        )
        
        data = response.json()
        
        if "outputs" not in data:
            error_msg = data.get("message", "Unbekannter Fehler")
            raise PVGISError(f"Ungültige Antwort: {error_msg}")
        
        if "hourly" not in data["outputs"]:
            raise PVGISError("Keine Stundenwerte in der Antwort")
        
        hourly_data = data["outputs"]["hourly"]
        if not hourly_data:
            raise PVGISError(f"Keine Daten für Jahr {year} verfügbar")
        
        return np.array([h["P"] for h in hourly_data]) / 1000
        
    except PVGISError:
        raise
    except requests.exceptions.JSONDecodeError:
        raise PVGISError("Ungültige JSON-Antwort vom Server")
    except KeyError as e:
        raise PVGISError(f"Unerwartetes Datenformat: {e}")


def _extract_place_name(address: dict, display_name: str) -> str:
    """
    Extract a short, readable place name from Nominatim address data.
    
    Nominatim returns structured address data with fields like 'city', 'town',
    'village', etc. This function extracts the most relevant place name.
    
    Args:
        address: Nominatim address object (from addressdetails=1)
        display_name: Fallback display_name if no city found
        
    Returns:
        Short place name like "München, Bayern" or just "München"
    """
    city = (
        address.get("city") or 
        address.get("town") or 
        address.get("village") or 
        address.get("municipality") or
        address.get("county")
    )
    state = address.get("state", "")
    
    if city:
        return f"{city}, {state}" if state else city
    
    # Fallback: first part of display_name (but skip house numbers)
    parts = [p.strip() for p in display_name.split(",")]
    # Skip parts that look like house numbers or postal codes
    for part in parts:
        if part and not part[0].isdigit():
            return part
    
    return parts[0] if parts else display_name


@st.cache_data(show_spinner=False)
def geocode(query: str) -> tuple[str, str, float, float] | None:
    """
    Look up coordinates for a place name via Nominatim.
    
    Args:
        query: Place name to search for
        
    Returns:
        Tuple of (display_name, short_place_name, lat, lon) or None if not found.
        - display_name: Full address string from Nominatim
        - short_place_name: Short readable name like "München, Bayern"
        
    Raises:
        GeocodingError: If geocoding is disabled, email not configured,
                        or the API request fails (not for "not found")
    """
    if not query or not query.strip():
        return None
    
    _check_nominatim_enabled()
    
    retry_config = RetryConfig(max_retries=2, base_delay=2.0)
    params = {
        "q": query, 
        "format": "json", 
        "limit": 1, 
        "addressdetails": 1,
        "email": NOMINATIM_EMAIL,
    }
    
    try:
        response = _retry_with_backoff(
            lambda: requests.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"User-Agent": "solarbatteryield-streamlit/1.0"},
                timeout=10,
            ),
            retry_config=retry_config,
            error_class=GeocodingError,
            service_name="Geocoding"
        )
        
        results = response.json()
        
        if results:
            r = results[0]
            display_name = r.get("display_name", query)
            address = r.get("address", {})
            short_name = _extract_place_name(address, display_name)
            return display_name, short_name, float(r["lat"]), float(r["lon"])
        
        return None
        
    except GeocodingError:
        raise
    except requests.exceptions.JSONDecodeError:
        raise GeocodingError("Ungültige Antwort vom Geocoding-Service")
    except (KeyError, ValueError) as e:
        raise GeocodingError(f"Unerwartetes Datenformat: {e}")


@st.cache_data(show_spinner=False)
def reverse_geocode(lat: float, lon: float) -> str | None:
    """
    Reverse look-up: return a short place name for coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        
    Returns:
        Place name string or None if lookup fails or geocoding is disabled
        
    Note:
        This function catches all exceptions and returns None on failure
        to avoid disrupting the main application flow. If geocoding is
        disabled or not properly configured, it silently returns None.
    """
    # Return None if geocoding is disabled or not properly configured
    if not NOMINATIM_ENABLED or not NOMINATIM_EMAIL:
        return None
    
    params = {
        "lat": lat, 
        "lon": lon, 
        "format": "json", 
        "zoom": 10, 
        "accept-language": "de",
        "email": NOMINATIM_EMAIL,
    }
    
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params=params,
            headers={"User-Agent": "solarbatteryield-streamlit/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        
        data = response.json()
        address = data.get("address", {})
        display_name = data.get("display_name", "")
        
        return _extract_place_name(address, display_name)
        
    except Exception:
        # Silently fail - this is non-critical functionality
        return None
