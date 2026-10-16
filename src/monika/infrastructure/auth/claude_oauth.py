# ==============================================================================
# File: infrastructure/auth/claude_oauth.py
# ==============================================================================

"""
Claude (Anthropic) OAuth Integration & Credential Resolver.
Supports:
1. Auto-adopting credentials from Claude Code CLI (~/.claude/.credentials.json).
2. Autonomous token refreshing via Anthropic's OAuth token endpoint.
3. Interactive PKCE OAuth login when Claude Code CLI is not installed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request

from monika.infrastructure.auth.oauth_store import (
    get_oauth_tokens,
    is_token_expiring,
    save_oauth_tokens,
)

logger = logging.getLogger("TradingAgent.Auth.ClaudeOAuth")

CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_OAUTH_TOKEN_URLS = [
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
]
CLAUDE_OAUTH_TOKEN_USER_AGENT = "axios/1.7.9"
CLAUDE_OAUTH_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
CLAUDE_OAUTH_SCOPES = "org:create_api_key user:profile user:inference"
CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"


def get_claude_credentials_path() -> Path:
    """Return the path to Claude Code CLI credentials file."""
    override = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    root = Path(override).expanduser() if override else Path.home() / ".claude"
    return root / ".credentials.json"


def read_claude_code_credentials_file() -> Optional[Dict[str, Any]]:
    """Read credentials written by Claude Code CLI (~/.claude/.credentials.json)."""
    creds_path = get_claude_credentials_path()
    if not creds_path.exists():
        return None
    try:
        data = json.loads(creds_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        oauth_data = data.get("claudeAiOauth")
        if not isinstance(oauth_data, dict):
            return None
        access_token = oauth_data.get("accessToken", "").strip()
        if not access_token:
            return None
        return {
            "access_token": access_token,
            "refresh_token": oauth_data.get("refreshToken", "").strip(),
            "expires_at": oauth_data.get("expiresAt", 0),
            "source": "claude_code_file",
        }
    except Exception as exc:
        logger.debug("Failed to read Claude Code credentials file: %s", exc)
        return None


def read_claude_code_keychain() -> Optional[Dict[str, Any]]:
    """Read macOS Keychain entry for Claude Code credentials if on Darwin."""
    if platform.system() != "Darwin":
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", CLAUDE_KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout.strip())
        oauth_data = data.get("claudeAiOauth") if isinstance(data, dict) else None
        if not isinstance(oauth_data, dict) or not oauth_data.get("accessToken"):
            return None
        return {
            "access_token": oauth_data.get("accessToken", "").strip(),
            "refresh_token": oauth_data.get("refreshToken", "").strip(),
            "expires_at": oauth_data.get("expiresAt", 0),
            "source": "macos_keychain",
        }
    except Exception as exc:
        logger.debug("Keychain read skipped or failed: %s", exc)
        return None


def read_claude_code_credentials() -> Optional[Dict[str, Any]]:
    """Read Claude Code credentials from file or Keychain."""
    return read_claude_code_credentials_file() or read_claude_code_keychain()


def refresh_claude_token(refresh_token: str | Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Exchange a refresh token for a fresh access token with Anthropic OAuth endpoint."""
    token_str = (
        refresh_token.get("refresh_token", "") if isinstance(refresh_token, dict) else str(refresh_token)
    ).strip()
    if not token_str:
        return None

    payload = json.dumps(
        {
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": token_str,
        }
    ).encode("utf-8")

    for url in CLAUDE_OAUTH_TOKEN_URLS:
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": CLAUDE_OAUTH_TOKEN_USER_AGENT,
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and data.get("access_token"):
                    expires_in = data.get("expires_in", 3600)
                    token_record = {
                        "access_token": data["access_token"].strip(),
                        "refresh_token": str(data.get("refresh_token") or token_str).strip(),
                        "expires_at": time.time() + float(expires_in),
                        "token_type": data.get("token_type", "Bearer"),
                        "source": "anthropic_refresh",
                    }
                    save_oauth_tokens("anthropic", token_record)
                    logger.info("Successfully refreshed Claude OAuth access token.")
                    return token_record
        except Exception as exc:
            logger.debug("Claude token refresh attempt at %s failed: %s", url, exc)
            continue

    logger.warning("All Claude token refresh attempts failed.")
    return None


def resolve_claude_access_token() -> Optional[str]:
    """
    Resolve active and valid Claude access token:
    1. Checks Monika's internal OAuth store.
    2. If expiring or absent, checks Claude Code CLI credentials.
    3. Triggers refresh if token is expired but refresh_token exists.
    4. Returns active access token string or None.
    """
    token_record = get_oauth_tokens("anthropic")

    # If no local store record or missing access token, try adopting from Claude Code CLI
    if not token_record or not token_record.get("access_token"):
        cli_creds = read_claude_code_credentials()
        if cli_creds:
            token_record = cli_creds
            save_oauth_tokens("anthropic", token_record)
            logger.info("Adopted Claude Code CLI OAuth credentials into Monika.")

    if not token_record:
        return None

    # Check expiration
    if is_token_expiring(token_record, skew_seconds=180):
        refresh_token = token_record.get("refresh_token")
        if refresh_token:
            refreshed = refresh_claude_token(refresh_token)
            if refreshed and refreshed.get("access_token"):
                return refreshed["access_token"]

    return token_record.get("access_token") or None


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE (code_verifier, code_challenge) using S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def get_claude_authorization_url(code_challenge: str, state: str) -> str:
    """Build Anthropic OAuth authorization URL for browser login."""
    params = {
        "client_id": CLAUDE_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": CLAUDE_OAUTH_REDIRECT_URI,
        "scope": CLAUDE_OAUTH_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"https://console.anthropic.com/oauth/authorize?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str, code_verifier: str) -> Optional[Dict[str, Any]]:
    """Exchange authorization code for token pair."""
    payload = json.dumps(
        {
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": CLAUDE_OAUTH_REDIRECT_URI,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")

    for url in CLAUDE_OAUTH_TOKEN_URLS:
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": CLAUDE_OAUTH_TOKEN_USER_AGENT,
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and data.get("access_token"):
                    expires_in = data.get("expires_in", 3600)
                    token_record = {
                        "access_token": data["access_token"].strip(),
                        "refresh_token": data.get("refresh_token", "").strip(),
                        "expires_at": time.time() + float(expires_in),
                        "token_type": data.get("token_type", "Bearer"),
                        "source": "pkce_flow",
                    }
                    save_oauth_tokens("anthropic", token_record)
                    return token_record
        except Exception as exc:
            logger.debug("Anthropic authorization code exchange failed at %s: %s", url, exc)
            continue
    return None
