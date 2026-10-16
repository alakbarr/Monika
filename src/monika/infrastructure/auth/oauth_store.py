# ==============================================================================
# File: infrastructure/auth/oauth_store.py
# ==============================================================================

"""
Secure OAuth Token Store for Monika Trading Agent.
Manages encrypted storage, retrieval, and expiration tracking of OAuth tokens
using Monika's institutional Credential Vault (Windows Credential Manager / Fernet AES-128).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Optional

from monika.core.security.credential_vault import vault

logger = logging.getLogger("TradingAgent.Auth.OAuthStore")


def _provider_key(provider: str) -> str:
    """Normalize provider name into a vault secret key."""
    return f"OAUTH_TOKEN_{provider.strip().upper().replace('-', '_')}"


def decode_jwt_claims(jwt_token: str) -> dict[str, Any]:
    """Safely decode unverified claims from a JWT payload without external dependencies."""
    if not jwt_token or "." not in jwt_token:
        return {}
    parts = jwt_token.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    # Handle base64url padding
    remainder = len(payload_b64) % 4
    if remainder > 0:
        payload_b64 += "=" * (4 - remainder)
    try:
        decoded_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        data = json.loads(decoded_bytes.decode("utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("Failed to decode JWT claims: %s", exc)
        return {}


def save_oauth_tokens(provider: str, token_data: dict[str, Any]) -> bool:
    """
    Encrypt and store OAuth tokens for a specific provider in CredentialVault.
    token_data typically contains: access_token, refresh_token, expires_at, etc.
    """
    if not provider or not isinstance(token_data, dict):
        return False
    key = _provider_key(provider)
    try:
        payload = json.dumps(token_data)
        success = vault.set_secret(key, payload)
        if success:
            logger.info("Successfully persisted OAuth credentials for %s", provider)
        return success
    except Exception as exc:
        logger.error("Failed to store OAuth credentials for %s: %s", provider, exc)
        return False


def get_oauth_tokens(provider: str) -> Optional[dict[str, Any]]:
    """Retrieve and decrypt OAuth tokens for a specific provider from CredentialVault."""
    if not provider:
        return None
    key = _provider_key(provider)
    raw = vault.get_secret(key)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("Failed to parse decrypted OAuth tokens for %s: %s", provider, exc)
        return None


def delete_oauth_tokens(provider: str) -> bool:
    """Delete OAuth tokens for a specific provider from CredentialVault."""
    if not provider:
        return False
    key = _provider_key(provider)
    return vault.delete_secret(key)


def list_authenticated_providers() -> list[str]:
    """Return list of provider names that currently have active tokens stored in vault."""
    known = ["anthropic", "codex", "zai", "gemini"]
    return [p for p in known if get_oauth_tokens(p) is not None]


def get_token_expiry_timestamp(token_data: dict[str, Any]) -> Optional[float]:
    """
    Extract the expiration UNIX timestamp from token_data:
    1. Direct 'expires_at' field (seconds or milliseconds).
    2. Decoded JWT 'exp' claim from 'access_token'.
    3. Calculation from 'expires_in' if stamped with 'created_at'.
    """
    if not isinstance(token_data, dict):
        return None

    exp = token_data.get("expires_at")
    if isinstance(exp, (int, float)) and exp > 0:
        # Check if timestamp is in milliseconds (> year 3000 in seconds)
        return float(exp / 1000.0 if exp > 1e11 else exp)

    # Check JWT claims inside access_token
    access_token = token_data.get("access_token") or token_data.get("accessToken")
    if isinstance(access_token, str):
        claims = decode_jwt_claims(access_token)
        jwt_exp = claims.get("exp")
        if isinstance(jwt_exp, (int, float)) and jwt_exp > 0:
            return float(jwt_exp)

    # Check expires_in + created_at
    expires_in = token_data.get("expires_in")
    created_at = token_data.get("created_at")
    if isinstance(expires_in, (int, float)) and isinstance(created_at, (int, float)):
        return float(created_at + expires_in)

    return None


def is_token_expiring(token_data: dict[str, Any], skew_seconds: int = 120) -> bool:
    """
    Check if the token is already expired or expiring within `skew_seconds`.
    Returns True if expiring or if expiration cannot be determined while access_token is missing.
    """
    if not isinstance(token_data, dict):
        return True

    access_token = token_data.get("access_token") or token_data.get("accessToken")
    if not access_token:
        return True

    expiry_ts = get_token_expiry_timestamp(token_data)
    if expiry_ts is None:
        # If no expiry info is found, assume valid as long as access_token exists
        return False

    return time.time() >= (expiry_ts - max(0, skew_seconds))
