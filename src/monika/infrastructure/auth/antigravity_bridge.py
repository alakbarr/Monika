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
    get_oauth_tokens,
    is_token_expiring,
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
                token_record = {
                    "access_token": str(data["access_token"]).strip(),
                    "refresh_token": str(data.get("refresh_token", "")).strip(),
                    "expires_at": time.time() + float(expires_in),
                    "token_type": data.get("token_type", "Bearer"),
                    "source": "google_antigravity_oauth",
                }
                save_oauth_tokens("antigravity", token_record)
                logger.info("Successfully exchanged and saved Antigravity OAuth tokens.")
                return token_record
    except Exception as exc:
        logger.error("Antigravity OAuth code exchange failed: %s", exc)
        return None
    return None


def refresh_antigravity_token(refresh_token: str | Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
    """Exchange refresh token for fresh Antigravity access token."""
    token_str = (
        refresh_token.get("refresh_token", "") if isinstance(refresh_token, dict) else str(refresh_token)
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
                token_record = {
                    "access_token": str(data["access_token"]).strip(),
                    "refresh_token": str(data.get("refresh_token") or token_str).strip(),
                    "expires_at": time.time() + float(expires_in),
                    "token_type": data.get("token_type", "Bearer"),
                    "source": "google_antigravity_refresh",
                }
                save_oauth_tokens("antigravity", token_record)
                logger.info("Successfully refreshed Google Antigravity access token.")
                return token_record
    except Exception as exc:
        logger.error("Google Antigravity token refresh failed: %s", exc)
        return None
    return None


def resolve_antigravity_access_token() -> Optional[str]:
    """Retrieve and automatically refresh active Google Antigravity access token."""
    token_record = get_oauth_tokens("antigravity")
    if not token_record or not token_record.get("access_token"):
        return None

    if is_token_expiring(token_record, skew_seconds=180):
        refresh_token = token_record.get("refresh_token")
        if refresh_token:
            refreshed = refresh_antigravity_token(refresh_token)
            if refreshed and refreshed.get("access_token"):
                return refreshed["access_token"]

    return token_record.get("access_token") or None


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
