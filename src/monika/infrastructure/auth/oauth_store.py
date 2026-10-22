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
from typing import Any

from monika.core.security.credential_vault import vault

logger = logging.getLogger(__name__)


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
        success = vault.set_secret(key, payload, persist_to_os=True)
        if success:
            logger.info("Successfully persisted OAuth credentials for %s", provider)
            email = token_data.get("email")
            if email:
                accounts = get_oauth_accounts(provider)
                target_id = email.strip().lower()
                updated = False
                new_accounts: list[dict[str, Any]] = []
                for acc in accounts:
                    curr_id = (acc.get("email") or acc.get("account_id") or "").strip().lower()
                    if target_id and curr_id == target_id:
                        merged = dict(acc)
                        merged.update(token_data)
                        new_accounts.append(merged)
                        updated = True
                    else:
                        new_accounts.append(acc)
                if not updated:
                    new_accounts.append(dict(token_data))
                p_key = _accounts_key(provider)
                vault.set_secret(p_key, json.dumps(new_accounts), persist_to_os=True)
        return success
    except Exception as exc:
        logger.error("Failed to store OAuth credentials for %s: %s", provider, exc)
        return False


def get_oauth_tokens(provider: str) -> dict[str, Any] | None:
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


def _accounts_key(provider: str) -> str:
    """Normalize provider name into an account pool vault key."""
    return f"OAUTH_ACCOUNTS_{provider.strip().upper().replace('-', '_')}"


def save_oauth_account(
    provider: str,
    account_data: dict[str, Any],
    account_id: str | None = None,
) -> bool:
    """
    Save or update an account record within a provider's multi-account OAuth pool.
    Matches accounts by email, account_id, or sub.
    Maintains backward compatibility by also keeping the primary/paid account in OAUTH_TOKEN_<PROVIDER>.
    """
    if not provider or not isinstance(account_data, dict):
        return False

    accounts = get_oauth_accounts(provider)
    target_id = (account_id or account_data.get("email") or account_data.get("account_id") or "").strip().lower()

    updated = False
    new_accounts: list[dict[str, Any]] = []
    for acc in accounts:
        curr_id = (acc.get("email") or acc.get("account_id") or "").strip().lower()
        if target_id and curr_id == target_id:
            merged = dict(acc)
            merged.update(account_data)
            new_accounts.append(merged)
            updated = True
        else:
            new_accounts.append(acc)

    if not updated:
        new_record = dict(account_data)
        if target_id and "email" not in new_record:
            new_record["email"] = target_id
        new_accounts.append(new_record)

    key = _accounts_key(provider)
    try:
        payload = json.dumps(new_accounts)
        success = vault.set_secret(key, payload, persist_to_os=True)
        if success:
            logger.info("Successfully persisted OAuth account pool for %s (%d accounts)", provider, len(new_accounts))
            # Also keep single token synced with paid or first account
            paid_acc = next((a for a in new_accounts if a.get("tier") == "paid"), new_accounts[0])
            save_oauth_tokens(provider, paid_acc)
        return success
    except Exception as exc:
        logger.error("Failed to store OAuth account pool for %s: %s", provider, exc)
        return False


def get_oauth_accounts(provider: str) -> list[dict[str, Any]]:
    """Retrieve all accounts registered in a provider's OAuth pool."""
    if not provider:
        return []
    key = _accounts_key(provider)
    raw = vault.get_secret(key)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [a for a in data if isinstance(a, dict)]
        except Exception as exc:
            logger.warning("Failed to parse OAuth accounts pool for %s: %s", provider, exc)

    # Legacy fallback: if single token exists, wrap it as single account
    single = get_oauth_tokens(provider)
    if single and isinstance(single, dict) and single.get("access_token"):
        return [single]
    return []


def delete_oauth_account(provider: str, identifier: str) -> bool:
    """Remove a specific account by email, account_id, or 1-based slot index."""
    if not provider or not identifier:
        return False
    accounts = get_oauth_accounts(provider)
    if not accounts:
        return False

    ident_clean = str(identifier).strip().lower()
    filtered: list[dict[str, Any]] = []
    for idx, acc in enumerate(accounts, start=1):
        email = (acc.get("email") or "").strip().lower()
        acc_id = (acc.get("account_id") or "").strip().lower()
        if str(idx) == ident_clean or email == ident_clean or acc_id == ident_clean:
            continue
        filtered.append(acc)

    key = _accounts_key(provider)
    try:
        if filtered:
            payload = json.dumps(filtered)
            vault.set_secret(key, payload, persist_to_os=True)
            paid_acc = next((a for a in filtered if a.get("tier") == "paid"), filtered[0])
            save_oauth_tokens(provider, paid_acc)
        else:
            vault.delete_secret(key)
            delete_oauth_tokens(provider)
        return True
    except Exception as exc:
        logger.error("Failed to delete OAuth account %s for %s: %s", identifier, provider, exc)
        return False


def clear_oauth_accounts(provider: str) -> bool:
    """Clear all accounts from the provider pool."""
    if not provider:
        return False
    key = _accounts_key(provider)
    vault.delete_secret(key)
    return delete_oauth_tokens(provider)


def list_authenticated_providers() -> list[str]:
    """Return list of provider names that currently have active tokens stored in vault."""
    known = ["anthropic", "codex", "zai", "gemini", "antigravity"]
    return [p for p in known if get_oauth_tokens(p) is not None or get_oauth_accounts(p)]


def get_token_expiry_timestamp(token_data: dict[str, Any]) -> float | None:
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
