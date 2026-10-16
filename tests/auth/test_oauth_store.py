# ==============================================================================
# File: tests/auth/test_oauth_store.py
# ==============================================================================

"""
Unit tests for OAuth Credential Storage and Token Expiry Utilities.
"""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.auth.oauth_store import (
    delete_oauth_tokens,
    get_oauth_tokens,
    get_token_expiry_timestamp,
    is_token_expiring,
    list_authenticated_providers,
    save_oauth_tokens,
)


@pytest.fixture
def mock_vault():
    """Isolated in-memory vault for testing without touching OS keyring or disk."""
    store = {}
    with patch("monika.infrastructure.auth.oauth_store.vault") as v:
        v.get_secret.side_effect = lambda k, *args, **kwargs: store.get(k)
        v.set_secret.side_effect = lambda k, val, *args, **kwargs: store.update({k: val}) or True
        v.delete_secret.side_effect = lambda k, *args, **kwargs: bool(store.pop(k, None))
        yield store


def test_save_and_get_oauth_tokens(mock_vault):
    tokens = {
        "access_token": "test-access-token-123",
        "refresh_token": "test-refresh-token-456",
        "expires_in": 3600,
    }
    save_oauth_tokens("anthropic", tokens)

    retrieved = get_oauth_tokens("anthropic")
    assert retrieved is not None
    assert retrieved["access_token"] == "test-access-token-123"
    assert retrieved["refresh_token"] == "test-refresh-token-456"


def test_delete_oauth_tokens(mock_vault):
    tokens = {"access_token": "tok"}
    save_oauth_tokens("codex", tokens)
    assert get_oauth_tokens("codex") is not None

    delete_oauth_tokens("codex")
    assert get_oauth_tokens("codex") is None


def test_list_authenticated_providers(mock_vault):
    save_oauth_tokens("anthropic", {"access_token": "ant_tok"})
    save_oauth_tokens("codex", {"access_token": "cx_tok"})

    providers = list_authenticated_providers()
    assert "anthropic" in providers
    assert "codex" in providers
    assert "gemini" not in providers


def test_get_token_expiry_timestamp_from_jwt():
    # Construct a valid unpadded JWT payload with exp in the future
    future_exp = int(time.time()) + 1800
    payload = json.dumps({"sub": "user_123", "exp": future_exp}).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    fake_jwt = f"header.{b64_payload}.signature"

    token_data = {"access_token": fake_jwt}
    exp_ts = get_token_expiry_timestamp(token_data)
    assert exp_ts == float(future_exp)


def test_get_token_expiry_timestamp_from_explicit_field():
    future_exp = time.time() + 7200
    token_data = {"access_token": "opaque_token", "expires_at": future_exp}
    assert get_token_expiry_timestamp(token_data) == future_exp


def test_is_token_expiring_scenarios():
    now = time.time()

    # Case 1: Expired
    expired_data = {"access_token": "tok", "expires_at": now - 100}
    assert is_token_expiring(expired_data) is True

    # Case 2: Near expiry (< 300s buffer)
    near_expiry_data = {"access_token": "tok", "expires_at": now + 150}
    assert is_token_expiring(near_expiry_data, skew_seconds=300) is True

    # Case 3: Fresh token (> 300s buffer)
    fresh_data = {"access_token": "tok", "expires_at": now + 3600}
    assert is_token_expiring(fresh_data, skew_seconds=300) is False

    # Case 4: No expiration info (fail-safe returns False)
    no_exp_data = {"access_token": "opaque_permanent_key"}
    assert is_token_expiring(no_exp_data) is False
