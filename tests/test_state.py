"""
Tests for the state module.

The state module handles session state management and URL configuration sharing.
These tests focus on the encode/decode functionality which can be tested
independently of Streamlit's session state.
"""
import base64
import json
import sys
import zlib
from unittest.mock import MagicMock, patch

import pytest


class MockSessionState(dict):
    """Mock that behaves like Streamlit's session state (dict with attribute access)."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value


@pytest.fixture
def mock_streamlit():
    """Fixture that provides a properly mocked Streamlit module."""
    # Remove cached state module so it gets re-imported with the mock.
    # If solarbatteryield.state was already imported (e.g. by other tests
    # importing report/sidebar packages), it holds a stale reference to
    # the real streamlit.  Removing it forces a fresh import.
    _modules_to_reload = [
        k for k in sys.modules
        if k == "solarbatteryield.state" or k == "state"
    ]
    saved = {k: sys.modules.pop(k) for k in _modules_to_reload}

    mock_st = MagicMock()
    mock_st.session_state = MockSessionState()

    with patch.dict(sys.modules, {"streamlit": mock_st}):
        yield mock_st

    # Restore original modules so other tests are not affected
    sys.modules.update(saved)


class TestConfigEncoding:
    """Tests for configuration encoding and decoding."""

    def test_should_encode_and_decode_simple_config(self, mock_streamlit):
        """Should be able to encode and decode a configuration roundtrip."""
        # given
        mock_streamlit.session_state.update({
            "cfg_lat": 48.0,
            "cfg_lon": 11.0,
            "cfg_annual_kwh": 3000,
            "cfg_profile_mode": "Einfach",
            "modules": [{"id": 0, "name": "Süd", "peak": 2.0, "azi": 0, "slope": 35}],
            "storages": [{"id": 0, "name": "Ohne", "cap": 0.0, "cost": 0}],
            "next_mod_id": 1,
            "next_stor_id": 1,
            "_active_base": [200] * 24,
            "_flex_delta": [0] * 24,
            "_periodic_delta": [0] * 24,
        })

        from solarbatteryield.state import encode_config, decode_config

        # when
        encoded = encode_config()

        # Clear and decode
        original_modules = mock_streamlit.session_state["modules"].copy()
        mock_streamlit.session_state.clear()
        decode_config(encoded)

        # then
        assert mock_streamlit.session_state["cfg_lat"] == 48.0
        assert mock_streamlit.session_state["cfg_lon"] == 11.0
        assert mock_streamlit.session_state["modules"] == original_modules

    def test_should_produce_url_safe_encoded_string(self, mock_streamlit):
        """Should produce a URL-safe base64 encoded string."""
        # given
        mock_streamlit.session_state.update({
            "modules": [],
            "storages": [],
            "next_mod_id": 0,
            "next_stor_id": 0,
            "_active_base": [100] * 24,
            "_flex_delta": [0] * 24,
            "_periodic_delta": [0] * 24,
        })

        from solarbatteryield.state import encode_config

        # when
        encoded = encode_config()

        # then
        assert all(c.isalnum() or c in "-_=" for c in encoded)
        decoded_bytes = base64.urlsafe_b64decode(encoded)
        assert len(decoded_bytes) > 0

    def test_should_compress_config_data(self, mock_streamlit):
        """Should compress the configuration data to reduce URL length."""
        # given
        mock_streamlit.session_state.update({
            "cfg_lat": 48.0,
            "cfg_lon": 11.0,
            "modules": [{"id": i, "name": f"Module {i}", "peak": 1.0, "azi": 0, "slope": 35} for i in range(10)],
            "storages": [],
            "next_mod_id": 10,
            "next_stor_id": 0,
            "_active_base": [200] * 24,
            "_flex_delta": [0] * 24,
            "_periodic_delta": [0] * 24,
        })

        from solarbatteryield.state import encode_config

        # when
        encoded = encode_config()

        # Calculate what uncompressed would be
        data = {k: v for k, v in mock_streamlit.session_state.items() if
                not k.startswith("_") or k in ["_active_base", "_flex_delta", "_periodic_delta"]}
        data["_version"] = 4
        raw_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        uncompressed_b64 = base64.urlsafe_b64encode(raw_json).decode("ascii")

        # then
        # Compressed should be shorter than uncompressed
        assert len(encoded) < len(uncompressed_b64)

    def test_should_include_version_in_encoded_config(self, mock_streamlit):
        """Should include version number for future compatibility."""
        # given
        mock_streamlit.session_state.update({
            "modules": [],
            "storages": [],
            "next_mod_id": 0,
            "next_stor_id": 0,
            "_active_base": [],
            "_flex_delta": [],
            "_periodic_delta": [],
        })

        from solarbatteryield.state import encode_config

        # when
        encoded = encode_config()

        compressed = base64.urlsafe_b64decode(encoded)
        raw = zlib.decompress(compressed)
        data = json.loads(raw)

        # then
        assert "_version" in data
        assert isinstance(data["_version"], int)
        assert data["_version"] >= 1

    def test_should_handle_day_type_profiles(self, mock_streamlit):
        """Should include day-type profiles when enabled."""
        # given
        mock_streamlit.session_state.update({
            "cfg_use_day_types": True,
            "modules": [],
            "storages": [],
            "next_mod_id": 0,
            "next_stor_id": 0,
            "_active_base": [200] * 24,
            "_flex_delta": [0] * 24,
            "_periodic_delta": [0] * 24,
            "_profile_saturday": [150] * 24,
            "_profile_sunday": [100] * 24,
        })

        from solarbatteryield.state import encode_config, decode_config

        # when
        encoded = encode_config()

        mock_streamlit.session_state.clear()
        decode_config(encoded)

        # then
        assert mock_streamlit.session_state.get("cfg_use_day_types") is True
        assert mock_streamlit.session_state["_profile_saturday"] == [150] * 24
        assert mock_streamlit.session_state["_profile_sunday"] == [100] * 24

    def test_should_handle_custom_inverter_efficiency(self, mock_streamlit):
        """Should include custom inverter efficiency when preset is custom."""
        # given
        custom_efficiency = [94.5, 96.2, 96.8, 97.2, 97.1, 96.8]
        mock_streamlit.session_state.update({
            "cfg_inverter_efficiency_preset": "custom",
            "modules": [],
            "storages": [],
            "next_mod_id": 0,
            "next_stor_id": 0,
            "_active_base": [],
            "_flex_delta": [],
            "_periodic_delta": [],
            "_inverter_eff_custom": custom_efficiency,
        })

        from solarbatteryield.state import encode_config, decode_config

        # when
        encoded = encode_config()

        mock_streamlit.session_state.clear()
        decode_config(encoded)

        # then
        assert mock_streamlit.session_state["_inverter_eff_custom"] == custom_efficiency


class TestSessionStateHelpers:
    """Tests for session state helper functions."""

    def test_sv_should_return_value_from_session_state(self, mock_streamlit):
        """Should return value from session state when present."""
        # given
        mock_streamlit.session_state["cfg_lat"] = 48.5

        from solarbatteryield.state import sv

        # when
        result = sv("cfg_lat")

        # then
        assert result == 48.5

    def test_sv_should_return_default_when_key_missing(self, mock_streamlit):
        """Should return default value when key is not in session state."""
        # given
        # Empty session state
        from solarbatteryield.state import sv

        # when
        result = sv("cfg_nonexistent", default=50.0)

        # then
        assert result == 50.0

    def test_widget_value_should_return_empty_dict_when_key_exists(self, mock_streamlit):
        """Should return empty dict when key already exists in session state."""
        # given
        mock_streamlit.session_state["cfg_lat"] = 48.5

        from solarbatteryield.state import widget_value

        # when
        result = widget_value("cfg_lat", default=50.0)

        # then
        assert result == {}

    def test_widget_value_should_return_value_dict_when_key_missing(self, mock_streamlit):
        """Should return dict with value when key is not in session state."""
        # given
        # Empty session state
        from solarbatteryield.state import widget_value

        # when
        result = widget_value("cfg_lat", default=50.0)

        # then
        assert result == {"value": 50.0}


class TestSessionIsolation:
    """Tests for session state isolation between users."""

    def test_default_modules_should_be_deeply_copied(self, mock_streamlit):
        """Default modules should be deep copied to prevent sharing between sessions.
        
        This is critical for security - without deep copy, modifying modules
        in one session would affect all other sessions using the defaults.
        """
        # given
        from solarbatteryield.config import DEFAULT_MODULES
        from solarbatteryield.state import init_session_state

        mock_streamlit.query_params = {}

        # when - simulate two different sessions initializing
        init_session_state()
        session1_modules = mock_streamlit.session_state["modules"]

        # Modify the module in session 1
        session1_modules[0]["name"] = "Modified by User 1"
        session1_modules[0]["peak"] = 99.9

        # then - the DEFAULT_MODULES should NOT be affected
        assert DEFAULT_MODULES[0]["name"] == "Süd", "DEFAULT_MODULES should not be modified"
        assert DEFAULT_MODULES[0]["peak"] == 2.0, "DEFAULT_MODULES should not be modified"

    def test_default_storages_should_be_deeply_copied(self, mock_streamlit):
        """Default storages should be deep copied to prevent sharing between sessions."""
        # given
        from solarbatteryield.config import DEFAULT_STORAGES
        from solarbatteryield.state import init_session_state

        mock_streamlit.query_params = {}

        # when - simulate session initializing
        init_session_state()
        session_storages = mock_streamlit.session_state["storages"]

        # Modify the storage in session
        session_storages[0]["name"] = "Modified Storage"
        session_storages[0]["cap"] = 999.0

        # then - the DEFAULT_STORAGES should NOT be affected
        assert DEFAULT_STORAGES[0]["name"] == "Klein", "DEFAULT_STORAGES should not be modified"
        assert DEFAULT_STORAGES[0]["cap"] == 2.0, "DEFAULT_STORAGES should not be modified"


class TestConfigDecoding:
    """Tests for configuration decoding edge cases."""

    def test_should_handle_missing_optional_fields(self, mock_streamlit):
        """Should handle configs without optional fields (backwards compatibility)."""
        # given
        minimal_data = {
            "modules": [],
            "storages": [],
            "_version": 1,
        }
        raw = json.dumps(minimal_data).encode("utf-8")
        compressed = zlib.compress(raw, level=9)
        encoded = base64.urlsafe_b64encode(compressed).decode("ascii")

        from solarbatteryield.state import decode_config

        # when
        decode_config(encoded)

        # then
        assert mock_streamlit.session_state["modules"] == []
        assert mock_streamlit.session_state["storages"] == []

    def test_should_restore_module_list(self, mock_streamlit):
        """Should correctly restore the module list with all properties."""
        # given
        modules = [
            {"id": 0, "name": "Süd", "peak": 2.0, "azi": 0, "slope": 35},
            {"id": 1, "name": "Ost", "peak": 1.5, "azi": -90, "slope": 30},
        ]
        data = {
            "modules": modules,
            "storages": [],
            "next_mod_id": 2,
            "next_stor_id": 0,
            "_version": 4,
        }
        raw = json.dumps(data).encode("utf-8")
        compressed = zlib.compress(raw, level=9)
        encoded = base64.urlsafe_b64encode(compressed).decode("ascii")

        from solarbatteryield.state import decode_config

        # when
        decode_config(encoded)

        # then
        assert mock_streamlit.session_state["modules"] == modules
        assert mock_streamlit.session_state["next_mod_id"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
