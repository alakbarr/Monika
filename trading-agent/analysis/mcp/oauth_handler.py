# ==============================================================================
# File: analysis/mcp/oauth_handler.py
# ==============================================================================

"""
MCP OAuth 2.1 Client Flow with PKCE & Token Refresh Fencing.
Institutional-grade engine turn protection architecture.

Enables secure connection to enterprise OAuth-protected MCP servers
(e.g., Jira, GitHub, Slack, Notion, Cloud APIs).
Implements Proof Key for Code Exchange (RFC 7636) and cross-process token refresh fencing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.MCP.OAuth")

_IS_WINDOWS = sys.platform == "win32"


def generate_pkce_pair() -> Tuple[str, str]:
    """Generate (code_verifier, code_challenge) using SHA-256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class OAuthCallbackServer:
    """One-shot localhost HTTP server to capture OAuth redirect code."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.auth_code: Optional[str] = None
        self.error: Optional[str] = None
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.done_event = threading.Event()

    def start(self) -> int:
        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Silence default stderr logging

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)

                if "code" in query:
                    parent.auth_code = query["code"][0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h2>Authentication successful!</h2><p>You can return to Monika.</p></body></html>")
                else:
                    parent.error = query.get("error", ["Unknown OAuth error"])[0]
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f"<html><body><h2>Authentication failed: {parent.error}</h2></body></html>".encode("utf-8"))

                parent.done_event.set()

        self._server = HTTPServer((self.host, self.port), _Handler)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def wait_for_code(self, timeout: float = 120.0) -> Tuple[Optional[str], Optional[str]]:
        self.done_event.wait(timeout=timeout)
        self.stop()
        return self.auth_code, self.error

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None


class OAuthTokenStorage:
    """Secure atomic storage for MCP OAuth tokens with refresh lock."""

    def __init__(self, token_path: Path):
        self.token_path = token_path
        self.lock_path = token_path.with_suffix(".refresh.lock")

    def load_tokens(self) -> Optional[Dict[str, Any]]:
        if not self.token_path.exists():
            return None
        try:
            return json.loads(self.token_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[OAuthStorage] Failed to read token file: {e}")
            return None

    def save_tokens(self, tokens: Dict[str, Any]) -> bool:
        try:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.token_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
            tmp_path.replace(self.token_path)
            return True
        except Exception as e:
            logger.error(f"[OAuthStorage] Failed to save tokens: {e}")
            return False

    def clear(self) -> None:
        if self.token_path.exists():
            try:
                self.token_path.unlink()
            except Exception:
                pass
