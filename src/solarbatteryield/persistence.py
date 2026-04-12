"""
URL shortening persistence layer using Amazon DynamoDB.

Provides short, shareable URLs for simulation configurations by storing them
in DynamoDB with a random key. Falls back gracefully to long URLs if DynamoDB
is unavailable.

The key design goals are:
- Short keys (8 characters) for easy sharing/typing
- Cryptographically random keys (not guessable/enumerable)
- In-memory caching to reduce DynamoDB reads
- Graceful fallback to long URLs on errors
- Automatic expiration after 3 months via DynamoDB TTL

Configuration (via st.secrets or environment variables):
    SOLARBATTERYIELD_DYNAMODB_TABLE: DynamoDB table name (default: "solarbatteryield")
    AWS_DEFAULT_REGION: AWS region (e.g., "eu-central-1")
    AWS_ACCESS_KEY_ID: AWS access key (or use IAM role)
    AWS_SECRET_ACCESS_KEY: AWS secret key (or use IAM role)
    DYNAMODB_ENDPOINT_URL: Optional custom endpoint (for local testing)
"""
from __future__ import annotations

import logging
import secrets
import time
from functools import lru_cache
from typing import Any

from solarbatteryield.utils import get_secret

logger = logging.getLogger(__name__)


# ─── Configuration ──────────────────────────────────────────────
# Table name from secrets/environment, default for local development
DYNAMODB_TABLE_NAME = get_secret("SOLARBATTERYIELD_DYNAMODB_TABLE", "solarbatteryield")

# Key length: 8 characters = ~47 bits of entropy (alphabet is base57)
# This gives ~111 trillion possible keys, making enumeration impractical
# while still being short enough to type
SHORT_KEY_LENGTH = 8

# Base57 alphabet: alphanumeric without ambiguous characters (0/O, 1/l/I)
# This makes keys easier to read and type correctly
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# Key prefixes for DynamoDB single-table design
PK_PREFIX = "SIM#"
SK_PREFIX = "CONFIG#"

# TTL for stored configs: 3 months in seconds
CONFIG_TTL_SECONDS = 90 * 24 * 60 * 60  # 90 days

# Cache TTL in seconds (1 hour)
# Prevents repeated reads for the same key during a session
CACHE_TTL_SECONDS = 3600

# Maximum cache size (LRU eviction)
CACHE_MAX_SIZE = 1000


# ─── In-Memory Cache ────────────────────────────────────────────
class TTLCache:
    """Simple TTL cache for config data to reduce DynamoDB reads."""

    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl: float = CACHE_TTL_SECONDS):
        self._cache: dict[str, tuple[str, float]] = {}
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str) -> str | None:
        """Get value if present and not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return value
            # Expired, remove it
            del self._cache[key]
        return None

    def set(self, key: str, value: str) -> None:
        """Set value with current timestamp."""
        # Simple LRU: if at capacity, remove oldest entry
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (value, time.time())

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()


# Global cache instance
_config_cache = TTLCache()


# ─── DynamoDB Client ────────────────────────────────────────────
@lru_cache(maxsize=1)
def _get_dynamodb_table() -> Any:
    """
    Get DynamoDB table resource, cached for reuse.
    
    Returns None if boto3 is not available or connection fails.
    Uses AWS credentials from st.secrets (Streamlit Cloud) or environment
    (IAM role, env vars, or credentials file).
    """
    try:
        import boto3
        from botocore.config import Config

        # Use shorter timeouts to fail fast
        config = Config(
            connect_timeout=2,
            read_timeout=5,
            retries={"max_attempts": 2}
        )

        # Check for local endpoint (for testing with DynamoDB Local)
        endpoint_url = get_secret("DYNAMODB_ENDPOINT_URL") or None

        # Get region and credentials from secrets/environment
        region_name = get_secret("AWS_DEFAULT_REGION") or None
        aws_access_key = get_secret("AWS_ACCESS_KEY_ID") or None
        aws_secret_key = get_secret("AWS_SECRET_ACCESS_KEY") or None

        # Build kwargs for boto3 resource
        resource_kwargs: dict[str, Any] = {
            "config": config,
            "region_name": region_name,
        }
        if endpoint_url:
            resource_kwargs["endpoint_url"] = endpoint_url
        if aws_access_key and aws_secret_key:
            resource_kwargs["aws_access_key_id"] = aws_access_key
            resource_kwargs["aws_secret_access_key"] = aws_secret_key

        dynamodb = boto3.resource("dynamodb", **resource_kwargs)
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)

        # Test connection by checking table status
        _ = table.table_status

        logger.debug(f"Connected to DynamoDB table: {DYNAMODB_TABLE_NAME}")
        return table

    except ImportError:
        logger.warning("boto3 not installed - short URLs disabled")
        return None
    except Exception as e:
        logger.warning(f"DynamoDB connection failed: {e}")
        return None


def _generate_short_key() -> str:
    """
    Generate a cryptographically random short key.
    
    Uses secrets module for secure randomness. The key is 8 characters
    from a base57 alphabet, providing ~47 bits of entropy.
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(SHORT_KEY_LENGTH))


# ─── Public API ─────────────────────────────────────────────────
def store_config(config_data: str) -> str | None:
    """
    Store configuration data and return a short key.
    
    Args:
        config_data: The encoded configuration string (base64 compressed JSON)
        
    Returns:
        Short key string if stored successfully, None on failure
    """
    table = _get_dynamodb_table()
    if table is None:
        return None

    try:
        # Generate new key
        short_key = _generate_short_key()
        
        # Calculate timestamps
        created_at = int(time.time())
        expire_at = created_at + CONFIG_TTL_SECONDS

        # Store with conditional write to avoid key collision
        # (extremely unlikely with 48 bits of entropy, but be safe)
        table.put_item(
            Item={
                "PK": f"{PK_PREFIX}{short_key}",
                "SK": f"{SK_PREFIX}{created_at}",
                "ConfigData": config_data,
                "ExpireAt": expire_at,
            },
            ConditionExpression="attribute_not_exists(PK)",
        )

        # Cache locally
        _config_cache.set(short_key, config_data)

        logger.debug(f"Stored config with key: {short_key}")
        return short_key

    except Exception as e:
        # Handle conditional check failure (key collision) - retry once
        if "ConditionalCheckFailedException" in str(type(e).__name__):
            try:
                short_key = _generate_short_key()
                created_at = int(time.time())
                expire_at = created_at + CONFIG_TTL_SECONDS
                table.put_item(
                    Item={
                        "PK": f"{PK_PREFIX}{short_key}",
                        "SK": f"{SK_PREFIX}{created_at}",
                        "ConfigData": config_data,
                        "ExpireAt": expire_at,
                    },
                    ConditionExpression="attribute_not_exists(PK)",
                )
                _config_cache.set(short_key, config_data)
                return short_key
            except Exception:
                pass

        logger.warning(f"Failed to store config: {e}")
        return None


def load_config(short_key: str) -> str | None:
    """
    Load configuration data by short key.
    
    Args:
        short_key: The short key returned by store_config
        
    Returns:
        The configuration data string, or None if not found
        
    Uses local cache to reduce DynamoDB reads.
    """
    # Validate key format
    if not short_key or len(short_key) != SHORT_KEY_LENGTH:
        return None
    if not all(c in ALPHABET for c in short_key):
        return None

    # Check cache first
    cached = _config_cache.get(short_key)
    if cached is not None:
        logger.debug(f"Cache hit for key: {short_key}")
        return cached

    table = _get_dynamodb_table()
    if table is None:
        return None

    try:
        # Query by PK and SK prefix
        from boto3.dynamodb.conditions import Key
        
        response = table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"{PK_PREFIX}{short_key}") &
                Key("SK").begins_with(SK_PREFIX)
            ),
            ProjectionExpression="ConfigData",
            Limit=1,
        )

        items = response.get("Items", [])
        if items and "ConfigData" in items[0]:
            config_data = items[0]["ConfigData"]
            # Cache for future requests
            _config_cache.set(short_key, config_data)
            logger.debug(f"Loaded config for key: {short_key}")
            return config_data

        return None

    except Exception as e:
        logger.warning(f"Failed to load config: {e}")
        return None


def is_available() -> bool:
    """
    Check if DynamoDB persistence is available.
    
    Returns True if boto3 is installed and connection works.
    """
    return _get_dynamodb_table() is not None


def clear_cache() -> None:
    """Clear the local config cache."""
    _config_cache.clear()


def reset_connection() -> None:
    """Reset the DynamoDB connection (for testing)."""
    _get_dynamodb_table.cache_clear()
    _config_cache.clear()
