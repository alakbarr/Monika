# ==============================================================================
# File: infrastructure/auth/antigravity_bridge.py
# ==============================================================================

"""
Antigravity Bridge Manager for Google Gemini Subscription.
Provides connectivity checks, liveness probes, and configuration management
for the local Antigravity Bridge proxy (typically localhost:8877) communicating
with Google Antigravity CLI (`agy`) sessions.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.request
import urllib.error

logger = logging.getLogger("TradingAgent.Auth.AntigravityBridge")

DEFAULT_ANTIGRAVITY_PROXY_URL = os.environ.get("ANTIGRAVITY_PROXY_URL", "http://127.0.0.1:8877/v1")


def get_antigravity_home() -> Path:
    """Return path to Google Antigravity CLI data directory (~/.gemini/antigravity-cli)."""
    return Path.home() / ".gemini" / "antigravity-cli"


def is_antigravity_installed() -> bool:
    """Check if Antigravity CLI data directory exists."""
    home = get_antigravity_home()
    return home.exists() and (home / "settings.json").exists()


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
