# ==============================================================================
# File: infrastructure/auth/antigravity_bridge.py
# ==============================================================================

"""
Antigravity Bridge & Native Google OAuth Manager for Gemini Subscriptions.
Supports:
1. Native Google Antigravity Desktop OAuth 2.0 PKCE flow (PKCE + Google Accounts).
2. Autonomous token refresh via https://oauth2.googleapis.com/token.
3. Secure token storage in Monika CredentialVault.
4. Liveness probing for local Antigravity Bridge proxy if deployed.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Dict, Optional
import urllib.error
import urllib.parse
import urllib.request

from monika.infrastructure.auth.oauth_store import (
    clear_oauth_accounts,
    decode_jwt_claims,
    delete_oauth_account,
    get_oauth_accounts,
    get_oauth_tokens,
    is_token_expiring,
    save_oauth_account,
    save_oauth_tokens,
)

logger = logging.getLogger("TradingAgent.Auth.AntigravityBridge")

DEFAULT_ANTIGRAVITY_PROXY_URL = os.environ.get("ANTIGRAVITY_PROXY_URL", "http://127.0.0.1:8877/v1")

# Public Antigravity Desktop OAuth credentials (from Antigravity CLI binary distribution)
_PUBLIC_CLIENT_ID_PROJECT_NUM = "1071006060591"
_PUBLIC_CLIENT_ID_HASH = "tmhssin2h21lcre235vtolojh4g403ep"
_PUBLIC_CLIENT_SECRET_SUFFIX = "K58FWR486LdLJ1mLB8sXC4z6qDAf"

ANTIGRAVITY_CLIENT_ID = os.environ.get(
    "ANTIGRAVITY_CLIENT_ID",
    f"{_PUBLIC_CLIENT_ID_PROJECT_NUM}-{_PUBLIC_CLIENT_ID_HASH}.apps.googleusercontent.com",
)
ANTIGRAVITY_CLIENT_SECRET = os.environ.get(
    "ANTIGRAVITY_CLIENT_SECRET",
    f"GOCSPX-{_PUBLIC_CLIENT_SECRET_SUFFIX}",
)

GOOGLE_OAUTH_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

ANTIGRAVITY_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/cclog "
    "https://www.googleapis.com/auth/experimentsandconfigs"
)

DEFAULT_CALLBACK_PORT = 8085
CALLBACK_PATH = "/oauth2callback"


def get_antigravity_home() -> Path:
    """Return path to Google Antigravity CLI data directory (~/.gemini/antigravity-cli)."""
    return Path.home() / ".gemini" / "antigravity-cli"


def is_antigravity_installed() -> bool:
    """Check if Antigravity CLI data directory exists."""
    home = get_antigravity_home()
    return home.exists() and (home / "settings.json").exists()


def generate_antigravity_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def get_antigravity_authorization_url(
    code_challenge: str,
    state: str,
    redirect_uri: str = f"http://127.0.0.1:{DEFAULT_CALLBACK_PORT}{CALLBACK_PATH}",
) -> str:
    """Build official Google OAuth 2.0 authorization URL for browser login."""
    params = {
        "client_id": ANTIGRAVITY_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ANTIGRAVITY_OAUTH_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{GOOGLE_OAUTH_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_antigravity_code(
    code: str,
    code_verifier: str,
    redirect_uri: str = f"http://127.0.0.1:{DEFAULT_CALLBACK_PORT}{CALLBACK_PATH}",
    timeout: float = 15.0,
    tier: str = "free",
) -> Optional[Dict[str, Any]]:
    """Exchange authorization code for access and refresh tokens at Google OAuth endpoint."""
    form_data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "code_verifier": code_verifier,
            "client_id": ANTIGRAVITY_CLIENT_ID,
            "client_secret": ANTIGRAVITY_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_OAUTH_TOKEN_ENDPOINT,
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("access_token"):
                expires_in = data.get("expires_in", 3600)
                # Decode id_token to extract account email
                id_token = data.get("id_token", "")
                claims = decode_jwt_claims(id_token) if id_token else {}
                email = str(claims.get("email") or f"antigravity_user_{int(time.time())}@gmail.com").strip().lower()

                token_record = {
                    "email": email,
                    "access_token": str(data["access_token"]).strip(),
                    "refresh_token": str(data.get("refresh_token", "")).strip(),
                    "expires_at": time.time() + float(expires_in),
                    "token_type": data.get("token_type", "Bearer"),
                    "source": "google_antigravity_oauth",
                    "tier": str(tier).lower().strip(),
                }
                save_oauth_tokens("antigravity", token_record)
                logger.info("Successfully exchanged and saved Antigravity OAuth tokens for %s (tier=%s).", email, tier)
                return token_record
    except Exception as exc:
        logger.error("Antigravity OAuth code exchange failed: %s", exc)
        return None
    return None


def refresh_antigravity_token(refresh_token: str | Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
    """Exchange refresh token for fresh Antigravity access token."""
    account_meta = refresh_token if isinstance(refresh_token, dict) else {}
    token_str = (
        account_meta.get("refresh_token", "") if isinstance(refresh_token, dict) else str(refresh_token)
    ).strip()
    if not token_str:
        return None

    form_data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": token_str,
            "client_id": ANTIGRAVITY_CLIENT_ID,
            "client_secret": ANTIGRAVITY_CLIENT_SECRET,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_OAUTH_TOKEN_ENDPOINT,
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("access_token"):
                expires_in = data.get("expires_in", 3600)
                email = account_meta.get("email")
                tier = account_meta.get("tier", "free")
                token_record = {
                    "email": email,
                    "access_token": str(data["access_token"]).strip(),
                    "refresh_token": str(data.get("refresh_token") or token_str).strip(),
                    "expires_at": time.time() + float(expires_in),
                    "token_type": data.get("token_type", "Bearer"),
                    "source": "google_antigravity_refresh",
                    "tier": tier,
                }
                save_oauth_tokens("antigravity", token_record)
                logger.info("Successfully refreshed Google Antigravity access token for %s.", email or "primary")
                return token_record
    except Exception as exc:
        logger.error("Google Antigravity token refresh failed: %s", exc)
        return None
    return None


_antigravity_round_robin_idx: int = 0
_antigravity_account_cooldowns: dict[str, float] = {}


def mark_antigravity_account_cooldown(
    identifier: Optional[str] = None,
    cooldown_seconds: float = 300.0,
    *,
    account_id: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    """Mark an account (email or token) on cooldown after rate limit (HTTP 429) or transient error."""
    target = account_id or identifier
    duration = duration_seconds if duration_seconds is not None else cooldown_seconds
    if target:
        _antigravity_account_cooldowns[target.strip().lower()] = time.time() + duration


def get_antigravity_pool_summary() -> dict[str, Any]:
    """Return summary statistics of active Antigravity account pool."""
    accounts = get_oauth_accounts("antigravity")
    now = time.time()
    paid_count = sum(1 for a in accounts if a.get("tier") == "paid")
    free_count = sum(1 for a in accounts if a.get("tier") != "paid")
    healthy_count = 0
    for a in accounts:
        email = (a.get("email") or "").strip().lower()
        tok = (a.get("access_token") or "").strip()
        cd_email = _antigravity_account_cooldowns.get(email, 0)
        cd_tok = _antigravity_account_cooldowns.get(tok, 0)
        if cd_email <= now and cd_tok <= now:
            healthy_count += 1

    return {
        "total_accounts": len(accounts),
        "paid_accounts": paid_count,
        "free_accounts": free_count,
        "active_accounts": healthy_count,
        "healthy_accounts": healthy_count,
        "cooldown_accounts": len(accounts) - healthy_count,
        "accounts": accounts,
    }


def resolve_antigravity_access_token(
    tier: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Retrieve and automatically refresh active Google Antigravity access token from account pool.
    - If tier == 'paid' or model is 'gemini-4-argon' / 'pro': prefers paid/subscription account.
    - If tier == 'free' or general/flash model: round-robins across free tier accounts.
    - Automatically skips accounts currently in cooldown.
    """
    global _antigravity_round_robin_idx

    accounts = get_oauth_accounts("antigravity")
    if not accounts:
        token_record = get_oauth_tokens("antigravity")
        if token_record and token_record.get("access_token"):
            accounts = [token_record]
        else:
            return None

    now = time.time()
    is_paid_request = tier == "paid" or (bool(model) and ("argon" in str(model).lower() or "pro" in str(model).lower()))

    def is_healthy(acc: dict[str, Any]) -> bool:
        email = (acc.get("email") or "").strip().lower()
        tok = (acc.get("access_token") or "").strip()
        cd_email = _antigravity_account_cooldowns.get(email, 0)
        cd_tok = _antigravity_account_cooldowns.get(tok, 0)
        return cd_email <= now and cd_tok <= now

    paid_accs = [a for a in accounts if a.get("tier") == "paid"]
    free_accs = [a for a in accounts if a.get("tier") != "paid"]

    if is_paid_request:
        healthy_paid = [a for a in paid_accs if is_healthy(a)]
        if healthy_paid:
            selected_pool = healthy_paid
        elif not paid_accs:
            # If no paid accounts configured at all, try healthy free accounts
            selected_pool = [a for a in free_accs if is_healthy(a)]
        else:
            return None
    else:
        healthy_free = [a for a in free_accs if is_healthy(a)]
        if healthy_free:
            selected_pool = healthy_free
        else:
            # Fall back to healthy paid account if all free accounts are in cooldown
            healthy_paid = [a for a in paid_accs if is_healthy(a)]
            if healthy_paid:
                selected_pool = healthy_paid
            else:
                return None

    if not selected_pool:
        return None

    target_acc = selected_pool[_antigravity_round_robin_idx % len(selected_pool)]
    _antigravity_round_robin_idx += 1

    if is_token_expiring(target_acc, skew_seconds=180):
        refreshed = refresh_antigravity_token(target_acc)
        if refreshed and refreshed.get("access_token"):
            return refreshed["access_token"]

    return target_acc.get("access_token") or None


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Temporary local HTTP listener capturing Google OAuth callback redirect."""

    expected_state: str = ""
    captured_code: Optional[str] = None
    captured_error: Optional[str] = None
    ready: Optional[threading.Event] = None

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        state = (params.get("state") or [""])[0]
        error = (params.get("error") or [""])[0]
        code = (params.get("code") or [""])[0]

        cls = OAuthCallbackHandler
        if state != cls.expected_state:
            cls.captured_error = "OAuth state mismatch."
        elif error:
            cls.captured_error = error
        elif not code:
            cls.captured_error = "OAuth callback did not include a code."
        else:
            cls.captured_code = code

        ok = not cls.captured_error
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            "<html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
            "<h2 style='color:#4CAF50;'>Google Antigravity OAuth Complete!</h2>"
            "<p>Your session has been securely saved to Monika. You can close this tab and return to your terminal.</p>"
            "</body></html>"
            if ok
            else f"<html><body style='font-family:sans-serif;text-align:center;padding:50px;'><h2 style='color:#E25B45;'>Authentication Failed</h2><p>{cls.captured_error}</p></body></html>"
        )
        self.wfile.write(html.encode("utf-8"))
        if cls.ready:
            cls.ready.set()


_OAuthCallbackHandler = OAuthCallbackHandler


def check_antigravity_bridge_health(proxy_url: Optional[str] = None, timeout: float = 3.0) -> Dict[str, Any]:
    """
    Probe the local Antigravity proxy server to verify it is responsive and authenticated.
    Checks /models or the base endpoint.
    """
    base = (proxy_url or DEFAULT_ANTIGRAVITY_PROXY_URL).rstrip("/")
    probe_url = f"{base}/models"

    req = urllib.request.Request(
        probe_url,
        headers={"Accept": "application/json", "User-Agent": "Monika-TradingAgent/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            return {
                "running": True,
                "status_code": status,
                "proxy_url": base,
                "authenticated": status == 200,
                "message": "Antigravity Bridge is active and responsive.",
            }
    except urllib.error.HTTPError as err:
        return {
            "running": True,
            "status_code": err.code,
            "proxy_url": base,
            "authenticated": err.code != 401,
            "message": f"Bridge responded with HTTP {err.code}: {err.reason}",
        }
    except Exception as exc:
        return {
            "running": False,
            "status_code": None,
            "proxy_url": base,
            "authenticated": False,
            "message": f"Could not connect to Antigravity Bridge at {base}: {exc}",
        }
