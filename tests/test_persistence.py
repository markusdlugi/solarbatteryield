"""
Tests for the persistence module (DynamoDB short URL storage).

This module provides URL shortening for simulation configurations using DynamoDB.
Tests verify key generation, caching, validation, and DynamoDB integration.
"""
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest


# ─── Helper Functions ──────────────────────────────────────────────────────────

def _remove_persistence_modules() -> dict:
    """Remove persistence-related modules from sys.modules for fresh import."""
    saved = {}
    for key in list(sys.modules.keys()):
        if "solarbatteryield.persistence" in key or key == "boto3":
            saved[key] = sys.modules.pop(key)
    return saved


def _remove_state_modules() -> dict:
    """Remove state-related modules from sys.modules for fresh import."""
    saved = {}
    for key in list(sys.modules.keys()):
        if "solarbatteryield.state" in key or "solarbatteryield.persistence" in key:
            saved[key] = sys.modules.pop(key)
    return saved


class MockSessionState(dict):
    """Mock that behaves like Streamlit's session state (dict with attribute access)."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value


def _create_mock_streamlit() -> MagicMock:
    """Create a mock Streamlit module with minimal session state."""
    mock_st = MagicMock()
    mock_st.session_state = MockSessionState({
        "modules": [],
        "storages": [],
        "next_mod_id": 0,
        "next_stor_id": 0,
        "_active_base": [100] * 24,
        "_flex_delta": [0] * 24,
        "_periodic_delta": [0] * 24,
    })
    return mock_st


# ─── Test Classes ──────────────────────────────────────────────────────────────

class TestPersistenceWithoutBoto3:
    """Tests for persistence module behavior when boto3 is not installed."""

    def test_should_return_false_for_is_available_without_boto3(self):
        """Should return False when boto3 is not installed."""
        # given
        saved_modules = _remove_persistence_modules()
        
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
        
        def mock_import(name, *args, **kwargs):
            if name == "boto3" or name.startswith("boto3."):
                raise ImportError("No module named 'boto3'")
            return original_import(name, *args, **kwargs)
        
        try:
            with patch.dict(sys.modules, {"boto3": None}):
                with patch("builtins.__import__", mock_import):
                    if "solarbatteryield.persistence" in sys.modules:
                        del sys.modules["solarbatteryield.persistence"]
                    
                    from solarbatteryield.persistence import is_available, reset_connection
                    reset_connection()
                    
                    # when
                    result = is_available()
                    
                    # then
                    assert result is False
        finally:
            sys.modules.update(saved_modules)

    def test_should_return_none_from_store_config_without_boto3(self):
        """Should return None when storing config without boto3."""
        # given
        saved_modules = _remove_persistence_modules()
        
        try:
            with patch.dict(sys.modules, {"boto3": None}):
                from solarbatteryield.persistence import store_config, reset_connection
                reset_connection()
                
                # when
                result = store_config("test_config_data")
                
                # then
                assert result is None
        finally:
            sys.modules.update(saved_modules)

    def test_should_return_none_from_load_config_without_boto3(self):
        """Should return None when loading config without boto3."""
        # given
        saved_modules = _remove_persistence_modules()
        
        try:
            with patch.dict(sys.modules, {"boto3": None}):
                from solarbatteryield.persistence import load_config, reset_connection
                reset_connection()
                
                # when
                result = load_config("AbCd1234")
                
                # then
                assert result is None
        finally:
            sys.modules.update(saved_modules)


class TestShortKeyGeneration:
    """Tests for cryptographically random short key generation."""

    def test_should_generate_key_with_correct_length(self):
        """Should generate keys with exactly 8 characters."""
        # given
        from solarbatteryield.persistence import _generate_short_key, SHORT_KEY_LENGTH
        
        # when
        keys = [_generate_short_key() for _ in range(100)]
        
        # then
        assert all(len(key) == SHORT_KEY_LENGTH for key in keys)

    def test_should_generate_key_with_valid_alphabet(self):
        """Should only use base62 characters (alphanumeric)."""
        # given
        from solarbatteryield.persistence import _generate_short_key, ALPHABET
        
        # when
        keys = [_generate_short_key() for _ in range(100)]
        
        # then
        assert all(all(c in ALPHABET for c in key) for key in keys)

    def test_should_generate_unique_keys(self):
        """Should generate unique keys (with high probability)."""
        # given
        from solarbatteryield.persistence import _generate_short_key
        
        # when
        keys = {_generate_short_key() for _ in range(1000)}
        
        # then
        assert len(keys) == 1000, "All 1000 generated keys should be unique"


class TestKeyValidation:
    """Tests for key format validation in load_config."""

    def test_should_reject_empty_key(self):
        """Should return None for empty key string."""
        # given
        from solarbatteryield.persistence import load_config
        
        # when
        result = load_config("")
        
        # then
        assert result is None

    @pytest.mark.parametrize("key,description", [
        ("short", "too short (5 chars)"),
        ("toolongkey123", "too long (13 chars)"),
    ])
    def test_should_reject_key_with_wrong_length(self, key, description):
        """Should return None for keys that are not exactly 8 characters."""
        # given
        from solarbatteryield.persistence import load_config
        
        # when
        result = load_config(key)
        
        # then
        assert result is None, f"Should reject key that is {description}"

    @pytest.mark.parametrize("key,description", [
        ("AbCd!@#$", "contains special characters"),
        ("AbCd 123", "contains space"),
    ])
    def test_should_reject_key_with_invalid_characters(self, key, description):
        """Should return None for keys containing non-alphanumeric characters."""
        # given
        from solarbatteryield.persistence import load_config
        
        # when
        result = load_config(key)
        
        # then
        assert result is None, f"Should reject key that {description}"


class TestTTLCache:
    """Tests for the in-memory TTL cache used to reduce DynamoDB reads."""

    def test_should_store_and_retrieve_value(self):
        """Should store a value and retrieve it before expiration."""
        # given
        from solarbatteryield.persistence import TTLCache
        cache = TTLCache(ttl=60)
        
        # when
        cache.set("key1", "value1")
        result = cache.get("key1")
        
        # then
        assert result == "value1"

    def test_should_return_none_for_missing_key(self):
        """Should return None when key does not exist in cache."""
        # given
        from solarbatteryield.persistence import TTLCache
        cache = TTLCache()
        
        # when
        result = cache.get("nonexistent")
        
        # then
        assert result is None

    def test_should_expire_entries_after_ttl(self):
        """Should return None for entries that have expired."""
        # given
        from solarbatteryield.persistence import TTLCache
        cache = TTLCache(ttl=0.01)  # 10ms TTL
        cache.set("key1", "value1")
        
        # when
        time.sleep(0.02)  # Wait for expiry
        result = cache.get("key1")
        
        # then
        assert result is None

    def test_should_evict_oldest_entry_when_at_capacity(self):
        """Should remove oldest entry when max_size is reached."""
        # given
        from solarbatteryield.persistence import TTLCache
        cache = TTLCache(max_size=2, ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # when
        cache.set("key3", "value3")  # Should evict key1
        
        # then
        assert cache.get("key1") is None, "Oldest entry should be evicted"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_should_remove_all_entries_on_clear(self):
        """Should remove all entries when clear() is called."""
        # given
        from solarbatteryield.persistence import TTLCache
        cache = TTLCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # when
        cache.clear()
        
        # then
        assert cache.get("key1") is None
        assert cache.get("key2") is None



# ─── DynamoDB Integration Tests ────────────────────────────────────────────────

@pytest.fixture
def dynamodb_table():
    """Create a mocked DynamoDB table for testing."""
    try:
        import boto3
        from moto import mock_aws
    except ImportError:
        pytest.skip("moto or boto3 not installed")
    
    # Set AWS credentials and region for moto
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    
    # Remove cached persistence module to pick up new environment
    saved_persistence = {}
    for key in list(sys.modules.keys()):
        if "solarbatteryield.persistence" in key:
            saved_persistence[key] = sys.modules.pop(key)
    
    with mock_aws():
        # given: set up the table with PK and SK
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="solarbatteryield",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        
        # Import fresh persistence module within moto context
        from solarbatteryield.persistence import reset_connection
        reset_connection()
        
        yield table
        
        reset_connection()
    
    # Restore modules
    sys.modules.update(saved_persistence)


class TestDynamoDBIntegration:
    """Integration tests with mocked DynamoDB."""

    def test_should_store_and_load_config_roundtrip(self, dynamodb_table):
        """Should successfully store config and retrieve it by short key."""
        # given
        from solarbatteryield.persistence import store_config, load_config, reset_connection
        reset_connection()
        config_data = "eJwrySxK1M1NzSsBABNfA/o="  # Sample base64 encoded config
        
        # when
        short_key = store_config(config_data)
        loaded = load_config(short_key)
        
        # then
        assert short_key is not None
        assert len(short_key) == 8
        assert loaded == config_data

    def test_should_return_true_for_is_available_with_dynamodb(self, dynamodb_table):
        """Should return True when DynamoDB connection is successful."""
        # given
        from solarbatteryield.persistence import is_available, reset_connection
        reset_connection()
        
        # when
        result = is_available()
        
        # then
        assert result is True

    def test_should_return_none_for_nonexistent_key(self, dynamodb_table):
        """Should return None when loading a key that doesn't exist."""
        # given
        from solarbatteryield.persistence import load_config, reset_connection
        reset_connection()
        
        # when
        result = load_config("NotExist")
        
        # then
        assert result is None

    def test_should_cache_loaded_config(self, dynamodb_table):
        """Should cache config data after loading to prevent repeated reads."""
        # given
        from solarbatteryield.persistence import (
            store_config, load_config, _config_cache, reset_connection
        )
        reset_connection()
        config_data = "test_config"
        short_key = store_config(config_data)
        
        # when
        load_config(short_key)
        
        # then
        assert _config_cache.get(short_key) == config_data


class TestCreateShareUrl:
    """Tests for the create_share_url function in state module."""

    def test_should_fallback_to_long_url_without_dynamodb(self):
        """Should create long URL with embedded config when DynamoDB is unavailable."""
        # given
        mock_st = _create_mock_streamlit()
        saved = _remove_state_modules()
        
        try:
            with patch.dict(sys.modules, {"streamlit": mock_st, "boto3": None}):
                from solarbatteryield.state import create_share_url
                from solarbatteryield.persistence import reset_connection
                reset_connection()
                
                # when
                url, is_short = create_share_url("https://example.com")
                
                # then
                assert is_short is False
                assert url.startswith("https://example.com/?cfg=")
        finally:
            sys.modules.update(saved)

    def test_should_create_short_url_with_dynamodb(self, dynamodb_table):
        """Should create short URL with 8-character key when DynamoDB is available."""
        # given
        mock_st = _create_mock_streamlit()
        saved = {}
        for key in list(sys.modules.keys()):
            if "solarbatteryield.state" in key:
                saved[key] = sys.modules.pop(key)
        
        try:
            with patch.dict(sys.modules, {"streamlit": mock_st}):
                from solarbatteryield.state import create_share_url
                from solarbatteryield.persistence import reset_connection
                reset_connection()
                
                # when
                url, is_short = create_share_url("https://example.com")
                
                # then
                assert is_short is True
                assert url.startswith("https://example.com/?s=")
                short_key = url.split("?s=")[1]
                assert len(short_key) == 8
        finally:
            sys.modules.update(saved)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])









