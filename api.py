"""
External API integrations for the PV analysis application.
Handles PVGIS data fetching and geocoding via OpenStreetMap.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TypeVar

import numpy as np
import requests
import streamlit as st


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


# ─── Retry Logic ───────────────────────────────────────────────
T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    backoff_factor: float = 2.0


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


@st.cache_data(show_spinner=False, ttl=86400)
def geocode(query: str) -> tuple[str, float, float] | None:
    """
    Look up coordinates for a place name via Nominatim.
    
    Args:
        query: Place name to search for
        
    Returns:
        Tuple of (display_name, lat, lon) or None if not found
        
    Raises:
        GeocodingError: If the API request fails (not for "not found")
    """
    if not query or not query.strip():
        return None
    
    retry_config = RetryConfig(max_retries=2, base_delay=1.0)
    
    try:
        response = _retry_with_backoff(
            lambda: requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": "pv-analyse-streamlit/1.0"},
                timeout=10,
            ),
            retry_config=retry_config,
            error_class=GeocodingError,
            service_name="Geocoding"
        )
        
        results = response.json()
        
        if results:
            r = results[0]
            return r.get("display_name", query), float(r["lat"]), float(r["lon"])
        
        return None
        
    except GeocodingError:
        raise
    except requests.exceptions.JSONDecodeError:
        raise GeocodingError("Ungültige Antwort vom Geocoding-Service")
    except (KeyError, ValueError) as e:
        raise GeocodingError(f"Unerwartetes Datenformat: {e}")


@st.cache_data(show_spinner=False, ttl=86400)
def reverse_geocode(lat: float, lon: float) -> str | None:
    """
    Reverse look-up: return a short place name for coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        
    Returns:
        Place name string or None if lookup fails
        
    Note:
        This function catches all exceptions and returns None on failure
        to avoid disrupting the main application flow.
    """
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat, 
                "lon": lon, 
                "format": "json", 
                "zoom": 10, 
                "accept-language": "de"
            },
            headers={"User-Agent": "pv-analyse-streamlit/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        
        data = response.json()
        addr = data.get("address", {})
        city = (
            addr.get("city") or 
            addr.get("town") or 
            addr.get("village") or 
            addr.get("municipality")
        )
        state = addr.get("state", "")
        
        if city:
            return f"{city}, {state}" if state else city
        
        return data.get("display_name", "").split(",")[0] or None
        
    except Exception:
        # Silently fail - this is non-critical functionality
        return None
