"""
Tests for the API module.

The API module handles external API integrations including PVGIS data fetching
and OpenStreetMap geocoding. These tests verify the retry logic, error handling,
and response parsing without making actual API calls.
"""
import sys
from unittest.mock import MagicMock, patch, Mock

import pytest
import requests
import numpy as np


# ── Mock streamlit at module level BEFORE importing api ────────────────────────
# This avoids re-importing numpy (C extensions can't reload within a process).
# We need to remove any already-loaded modules that depend on streamlit.
_modules_to_remove = [k for k in sys.modules if 'solarbatteryield.api' in k or 'solarbatteryield.utils' in k]
_saved_modules = {k: sys.modules.pop(k) for k in _modules_to_remove}


def _passthrough_decorator(func=None, **kwargs):
    """Mock decorator that works both as @decorator and @decorator()."""
    if func is not None:
        # Called as @decorator without parentheses
        return func
    # Called as @decorator() with parentheses - return another decorator
    return lambda f: f


_mock_st = MagicMock()
_mock_st.cache_data = _passthrough_decorator

with patch.dict(sys.modules, {"streamlit": _mock_st}):
    import solarbatteryield.api as api_module
    from solarbatteryield.api import (
        RetryConfig,
        _retry_with_backoff,
        get_pvgis_hourly,
        geocode,
        reverse_geocode,
        PVAnalysisError,
        APIError,
        PVGISError,
        GeocodingError,
        ConfigurationError,
    )

# Reference to the requests module used inside api so we can patch it
_api_requests = api_module.requests


class TestRetryConfig:
    """Tests for retry configuration."""

    def test_should_have_default_retry_settings(self):
        """Should have sensible default retry settings."""
        # given/when
        config = RetryConfig()

        # then
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.backoff_factor == 2.0

    def test_should_allow_custom_retry_settings(self):
        """Should allow customizing retry settings."""
        # given/when
        config = RetryConfig(max_retries=5, base_delay=0.5, max_delay=10.0, backoff_factor=3.0)

        # then
        assert config.max_retries == 5
        assert config.base_delay == 0.5


class TestAPIExceptions:
    """Tests for API exception classes."""

    def test_should_create_pvgis_error_with_message(self):
        """Should create PVGISError with proper message format."""
        # given/when
        error = PVGISError("Test error message")

        # then
        assert "PVGIS" in str(error)
        assert "Test error message" in str(error)

    def test_should_create_pvgis_error_with_status_code(self):
        """Should store status code in PVGISError."""
        # given/when
        error = PVGISError("Test error", status_code=500)

        # then
        assert error.status_code == 500
        assert error.service == "PVGIS"

    def test_should_create_geocoding_error(self):
        """Should create GeocodingError with proper message format."""
        # given/when
        error = GeocodingError("Location not found")

        # then
        assert "Geocoding" in str(error)
        assert error.service == "Geocoding"

    def test_should_inherit_from_base_exception(self):
        """Should have PVAnalysisError as common base for all custom exceptions."""
        # given/when
        pvgis_err = PVGISError("test")
        geo_err = GeocodingError("test")
        config_err = ConfigurationError("test")

        # then
        assert isinstance(pvgis_err, PVAnalysisError)
        assert isinstance(geo_err, PVAnalysisError)
        assert isinstance(config_err, PVAnalysisError)


class TestRetryWithBackoff:
    """Tests for the retry with backoff logic."""

    def test_should_return_response_on_success(self):
        """Should return response immediately on successful request."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_func = Mock(return_value=mock_response)

        # when
        result = _retry_with_backoff(mock_func, RetryConfig())

        # then
        assert result == mock_response
        assert mock_func.call_count == 1

    def test_should_retry_on_timeout(self):
        """Should retry on timeout error."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        call_count = 0
        def failing_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.exceptions.Timeout()
            return mock_response

        config = RetryConfig(max_retries=3, base_delay=0.01)

        # when
        result = _retry_with_backoff(failing_then_ok, config)

        # then
        assert result == mock_response
        assert call_count == 2

    def test_should_raise_error_after_max_retries_on_timeout(self):
        """Should raise PVGISError after exhausting all retries on timeout."""
        # given
        def always_timeout():
            raise requests.exceptions.Timeout()

        config = RetryConfig(max_retries=2, base_delay=0.01)

        # when/then
        with pytest.raises(PVGISError) as exc_info:
            _retry_with_backoff(always_timeout, config, error_class=PVGISError)

        assert "Zeitüberschreitung" in str(exc_info.value)

    def test_should_raise_error_on_connection_failure(self):
        """Should raise error with connection message after retries exhausted."""
        # given
        def always_connection_error():
            raise requests.exceptions.ConnectionError()

        config = RetryConfig(max_retries=2, base_delay=0.01)

        # when/then
        with pytest.raises(PVGISError) as exc_info:
            _retry_with_backoff(always_connection_error, config, error_class=PVGISError)

        assert "Verbindungsfehler" in str(exc_info.value)

    def test_should_not_retry_on_client_error(self):
        """Should not retry on 4xx client errors."""
        # given
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status = Mock(
            side_effect=requests.exceptions.HTTPError(response=mock_response)
        )

        call_count = 0
        def client_error():
            nonlocal call_count
            call_count += 1
            return mock_response

        config = RetryConfig(max_retries=3, base_delay=0.01)

        # when/then
        with pytest.raises(PVGISError):
            _retry_with_backoff(client_error, config, error_class=PVGISError)

        assert call_count == 1

    def test_should_retry_on_server_error(self):
        """Should retry on 5xx server errors."""
        # given
        mock_success = Mock()
        mock_success.raise_for_status = Mock()

        call_count = 0
        def server_error_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                resp = Mock()
                resp.status_code = 500
                resp.raise_for_status = Mock(
                    side_effect=requests.exceptions.HTTPError(response=resp)
                )
                return resp
            return mock_success

        config = RetryConfig(max_retries=3, base_delay=0.01)

        # when
        result = _retry_with_backoff(server_error_then_ok, config)

        # then
        assert result == mock_success
        assert call_count == 2


class TestGetPvgisHourly:
    """Tests for PVGIS API integration."""

    def test_should_return_hourly_data_array(self):
        """Should return numpy array of hourly generation data."""
        # given
        hourly_data = [{"P": 1000.0} for _ in range(8760)]
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"outputs": {"hourly": hourly_data}}

        with patch.object(_api_requests, "get", return_value=mock_response):
            # when
            result = get_pvgis_hourly(lat=48.0, lon=11.0, peak=2.0, slope=35, azi=0, loss=10, year=2015)

        # then
        assert isinstance(result, np.ndarray)
        assert len(result) == 8760
        assert result[0] == pytest.approx(1.0)

    def test_should_convert_watts_to_kilowatts(self):
        """Should divide PVGIS power values by 1000 to convert W to kW."""
        # given
        hourly_data = [{"P": 500.0}, {"P": 250.0}]
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"outputs": {"hourly": hourly_data}}

        with patch.object(_api_requests, "get", return_value=mock_response):
            # when
            result = get_pvgis_hourly(lat=48.0, lon=11.0, peak=1.0, slope=35, azi=0, loss=10, year=2016)

        # then
        assert result[0] == pytest.approx(0.5)
        assert result[1] == pytest.approx(0.25)

    def test_should_raise_error_for_missing_outputs(self):
        """Should raise PVGISError when outputs are missing."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"message": "Invalid location"}

        with patch.object(_api_requests, "get", return_value=mock_response):
            # when/then
            with pytest.raises(PVGISError) as exc_info:
                get_pvgis_hourly(lat=91.0, lon=0.0, peak=1.0, slope=35, azi=0, loss=10, year=2017)

        assert "Ungültige Antwort" in str(exc_info.value)

    def test_should_raise_error_for_empty_data(self):
        """Should raise PVGISError when hourly data is empty."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"outputs": {"hourly": []}}

        with patch.object(_api_requests, "get", return_value=mock_response):
            # when/then
            with pytest.raises(PVGISError) as exc_info:
                get_pvgis_hourly(lat=48.0, lon=11.0, peak=1.0, slope=35, azi=0, loss=10, year=1990)

        assert "Keine Daten" in str(exc_info.value)

    def test_should_include_all_parameters_in_pvgis_url(self):
        """Should include all parameters in PVGIS API URL."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"outputs": {"hourly": [{"P": 100}]}}

        with patch.object(_api_requests, "get", return_value=mock_response) as mock_get:
            # when
            get_pvgis_hourly(lat=48.5, lon=11.5, peak=2.5, slope=30, azi=-10, loss=12, year=2020)

        # then
        url = mock_get.call_args[0][0]
        assert "lat=48.5" in url
        assert "lon=11.5" in url
        assert "peakpower=2.5" in url
        assert "angle=30" in url
        assert "aspect=-10" in url
        assert "loss=12" in url
        assert "startyear=2020" in url
        assert "endyear=2020" in url


class TestGeocode:
    """Tests for geocoding functionality."""

    def test_should_return_coordinates_for_valid_query(self):
        """Should return display name, short name, and coordinates for valid location."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = [{
            "display_name": "Munich, Bavaria, Germany",
            "lat": "48.1351",
            "lon": "11.5820",
            "address": {"city": "Munich", "state": "Bavaria", "country": "Germany"},
        }]

        with (
            patch.object(_api_requests, "get", return_value=mock_response),
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", "test@example.com"),
        ):
            # when
            result = geocode("Munich")

        # then
        assert result is not None
        display_name, short_name, lat, lon = result
        assert "Munich" in display_name
        assert short_name == "Munich, Bavaria"
        assert lat == pytest.approx(48.1351)
        assert lon == pytest.approx(11.5820)

    def test_should_return_none_for_no_results(self):
        """Should return None when no geocoding results found."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = []

        with (
            patch.object(_api_requests, "get", return_value=mock_response),
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", "test@example.com"),
        ):
            # when
            result = geocode("NonexistentPlace12345")

        # then
        assert result is None

    @pytest.mark.parametrize("query", ["", "   ", None])
    def test_should_return_none_for_empty_query(self, query):
        """Should return None for empty or whitespace query."""
        # given
        # (parameter provided by decorator)

        # when
        result = geocode(query)

        # then
        assert result is None

    def test_should_raise_error_when_disabled(self):
        """Should raise GeocodingError when geocoding is disabled."""
        # given
        with patch.object(api_module, "NOMINATIM_ENABLED", False):
            # when/then
            with pytest.raises(GeocodingError, match="deaktiviert"):
                geocode("Munich")

    def test_should_raise_error_when_email_not_set(self):
        """Should raise GeocodingError when email is not configured."""
        # given
        with (
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", ""),
        ):
            # when/then
            with pytest.raises(GeocodingError, match="NOMINATIM_EMAIL"):
                geocode("Munich")


class TestReverseGeocode:
    """Tests for reverse geocoding functionality."""

    def test_should_return_city_name_from_coordinates(self):
        """Should return city name from coordinates."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "display_name": "Munich, Bavaria, Germany",
            "address": {"city": "Munich", "state": "Bavaria"}
        }

        with (
            patch.object(_api_requests, "get", return_value=mock_response),
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", "test@example.com"),
        ):
            # when
            result = reverse_geocode(48.1351, 11.5820)

        # then
        assert result == "Munich, Bavaria"

    def test_should_fallback_to_town_if_no_city(self):
        """Should use town name if city is not available."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "display_name": "Kleinstadt, Hessen, Germany",
            "address": {"town": "Kleinstadt", "state": "Hessen"}
        }

        with (
            patch.object(_api_requests, "get", return_value=mock_response),
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", "test@example.com"),
        ):
            # when
            result = reverse_geocode(50.0, 8.0)

        # then
        assert result == "Kleinstadt, Hessen"

    def test_should_fallback_to_village_if_no_town(self):
        """Should use village name if neither city nor town is available."""
        # given
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "display_name": "Dorfhausen, Bayern, Germany",
            "address": {"village": "Dorfhausen", "state": "Bayern"}
        }

        with (
            patch.object(_api_requests, "get", return_value=mock_response),
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", "test@example.com"),
        ):
            # when
            result = reverse_geocode(47.5, 10.5)

        # then
        assert result == "Dorfhausen, Bayern"

    def test_should_return_none_on_error(self):
        """Should return None silently on any error."""
        # given
        with (
            patch.object(_api_requests, "get", side_effect=requests.exceptions.Timeout()),
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", "test@example.com"),
        ):
            # when
            result = reverse_geocode(48.0, 11.0)

        # then
        assert result is None

    def test_should_return_none_when_disabled(self):
        """Should return None silently when geocoding is disabled."""
        # given
        with patch.object(api_module, "NOMINATIM_ENABLED", False):
            # when
            result = reverse_geocode(48.0, 11.0)

        # then
        assert result is None

    def test_should_return_none_when_email_not_set(self):
        """Should return None silently when email is not configured."""
        # given
        with (
            patch.object(api_module, "NOMINATIM_ENABLED", True),
            patch.object(api_module, "NOMINATIM_EMAIL", ""),
        ):
            # when
            result = reverse_geocode(48.0, 11.0)

        # then
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])





