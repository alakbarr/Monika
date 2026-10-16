# ==============================================================================
# File: infrastructure/auth/codex_device_flow.py
# ==============================================================================

"""
OpenAI Codex Device Code OAuth Integration for ChatGPT Subscription.
Allows using ChatGPT Plus/Team/Pro subscription quota via OpenAI Codex Responses API.
Supports:
1. Interactive device code login (auth.openai.com/codex/device).
2. Autonomous token refreshing.
3. Auto-adopting credentials from OpenAI Codex CLI (~/.codex/auth.json).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request
import urllib.error

from monika.infrastructure.auth.oauth_store import (
    get_oauth_tokens,
    is_token_expiring,
    save_oauth_tokens,
)

logger = logging.getLogger("TradingAgent.Auth.CodexOAuth")

CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_ISSUER = "https://auth.openai.com"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


def get_codex_cli_auth_path() -> Path:
    """Return path to ~/.codex/auth.json."""
    return Path.home() / ".codex" / "auth.json"


def read_codex_cli_credentials() -> Optional[Dict[str, Any]]:
    """Read tokens from OpenAI Codex CLI if available."""
    raw_path = get_codex_cli_auth_path()
    auth_file = Path(raw_path) if not isinstance(raw_path, Path) else raw_path
    if not auth_file.exists():
        return None
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        raw_tokens = data.get("tokens")
        tokens_block: Dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else data
        access_token = str(tokens_block.get("access_token", "")).strip()
        refresh_token = str(tokens_block.get("refresh_token", "")).strip()
        account_id = str(tokens_block.get("account_id", "")).strip() or None
        if not access_token or not refresh_token:
            return None
        res: Dict[str, Any] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "source": "codex_cli_file",
        }
        if account_id:
            res["account_id"] = account_id
        return res
    except Exception as exc:
        logger.debug("Failed to read ~/.codex/auth.json: %s", exc)
        return None


def request_codex_device_code() -> Dict[str, Any]:
    """Step 1: Request user code and device auth ID from OpenAI."""
    url = f"{CODEX_OAUTH_ISSUER}/api/accounts/deviceauth/usercode"
    payload = json.dumps({"client_id": CODEX_OAUTH_CLIENT_ID}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        data["interval"] = max(3, int(data.get("interval", 5)))
        return data


def poll_codex_authorization(
    device_auth_id: str, user_code: str, poll_interval: int = 5, timeout: int = 600
) -> Dict[str, Any]:
    """Step 2: Poll OpenAI until user authorizes the device in the browser."""
    url = f"{CODEX_OAUTH_ISSUER}/api/accounts/deviceauth/token"
    payload = json.dumps({"device_auth_id": device_auth_id, "user_code": user_code}).encode("utf-8")
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        time.sleep(poll_interval)
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data
        except urllib.error.HTTPError as err:
            # 403 or 404 indicates user has not yet entered code/authorized
            if err.code in (403, 404):
                continue
            logger.warning("Codex device auth poll HTTP error %d: %s", err.code, err.reason)
        except Exception as exc:
            logger.debug("Transient poll error: %s", exc)
            continue

    raise TimeoutError("Codex device code authorization timed out.")


def exchange_codex_code(code_resp: Dict[str, Any]) -> Dict[str, Any]:
    """Step 3: Swap authorization code for OAuth tokens."""
    authorization_code = code_resp.get("authorization_code")
    code_verifier = code_resp.get("code_verifier")
    if not authorization_code or not code_verifier:
        raise ValueError("Missing authorization_code or code_verifier in response.")

    form_data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": f"{CODEX_OAUTH_ISSUER}/deviceauth/callback",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        CODEX_OAUTH_TOKEN_URL,
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))
        if not tokens.get("access_token"):
            raise ValueError("Token response missing access_token.")

        expires_in = tokens.get("expires_in", 86400)
        token_record = {
            "access_token": tokens["access_token"].strip(),
            "refresh_token": tokens.get("refresh_token", "").strip(),
            "expires_at": time.time() + float(expires_in),
            "token_type": tokens.get("token_type", "Bearer"),
            "source": "codex_device_flow",
        }
        save_oauth_tokens("codex", token_record)
        return token_record


def refresh_codex_token(refresh_token: str | Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Exchange refresh token for fresh Codex access token."""
    token_str = (
        refresh_token.get("refresh_token", "") if isinstance(refresh_token, dict) else str(refresh_token)
    ).strip()
    if not token_str:
        return None

    form_data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "refresh_token": token_str,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        CODEX_OAUTH_TOKEN_URL,
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
            if isinstance(tokens, dict) and tokens.get("access_token"):
                expires_in = tokens.get("expires_in", 86400)
                token_record = {
                    "access_token": tokens["access_token"].strip(),
                    "refresh_token": str(tokens.get("refresh_token") or token_str).strip(),
                    "expires_at": time.time() + float(expires_in),
                    "token_type": tokens.get("token_type", "Bearer"),
                    "source": "codex_refresh",
                }
                save_oauth_tokens("codex", token_record)
                logger.info("Successfully refreshed OpenAI Codex access token.")
                return token_record
    except Exception as exc:
        logger.warning("Codex token refresh failed: %s", exc)

    return None


def resolve_codex_access_token() -> Optional[str]:
    """Resolve active access token for OpenAI Codex."""
    token_record = get_oauth_tokens("codex")
    if not token_record or not token_record.get("access_token"):
        cli_tokens = read_codex_cli_credentials()
        if cli_tokens:
            token_record = cli_tokens
            save_oauth_tokens("codex", token_record)
            logger.info("Adopted OpenAI Codex CLI credentials into Monika.")

    if not token_record:
        return None

    if is_token_expiring(token_record, skew_seconds=180):
        refresh_token = token_record.get("refresh_token")
        if refresh_token:
            refreshed = refresh_codex_token(refresh_token)
            if refreshed and refreshed.get("access_token"):
                return refreshed["access_token"]

    return token_record.get("access_token") or None
