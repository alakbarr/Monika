# ==============================================================================
# File: tests/auth/test_antigravity_bridge.py
# ==============================================================================

"""
Unit tests for Google Gemini Antigravity Bridge detection and health check.
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.auth.antigravity_bridge import (
    DEFAULT_ANTIGRAVITY_PROXY_URL,
    check_antigravity_bridge_health,
    get_antigravity_home,
    is_antigravity_installed,
)


def test_is_antigravity_installed(tmp_path):
    mock_agy_dir = tmp_path / ".gemini" / "antigravity-cli"
    mock_agy_dir.mkdir(parents=True)
    (mock_agy_dir / "settings.json").touch()

    with patch("monika.infrastructure.auth.antigravity_bridge.get_antigravity_home", return_value=mock_agy_dir):
        assert is_antigravity_installed() is True

    nonexistent = tmp_path / "nonexistent" / "agy"
    with patch("monika.infrastructure.auth.antigravity_bridge.get_antigravity_home", return_value=nonexistent):
        assert is_antigravity_installed() is False


def test_check_antigravity_bridge_health_online():
    mock_resp_obj = MagicMock()
    mock_resp_obj.status = 200
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        health = check_antigravity_bridge_health("http://127.0.0.1:8877")
        assert health["running"] is True
        assert health["authenticated"] is True
        assert "active and responsive" in health["message"]


def test_check_antigravity_bridge_health_offline():
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        health = check_antigravity_bridge_health("http://127.0.0.1:8877")
        assert health["running"] is False
        assert health["authenticated"] is False
        assert "Could not connect" in health["message"]


def test_generate_antigravity_pkce():
    from monika.infrastructure.auth.antigravity_bridge import generate_antigravity_pkce

    verifier, challenge = generate_antigravity_pkce()
    assert len(verifier) >= 43
    assert len(challenge) > 0
    assert "=" not in challenge


def test_get_antigravity_authorization_url():
    from monika.infrastructure.auth.antigravity_bridge import get_antigravity_authorization_url

    url = get_antigravity_authorization_url(code_challenge="test_challenge", state="test_state")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert "code_challenge=test_challenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=test_state" in url
    assert "response_type=code" in url


def test_exchange_antigravity_code_success():
    from monika.infrastructure.auth.antigravity_bridge import exchange_antigravity_code

    mock_resp_data = json.dumps(
        {
            "access_token": "ya29.test_access_token",
            "refresh_token": "1//test_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with patch("monika.infrastructure.auth.antigravity_bridge.save_oauth_tokens") as mock_save:
            tokens = exchange_antigravity_code("test_code", "test_verifier")
            assert tokens is not None
            assert tokens["access_token"] == "ya29.test_access_token"
            assert tokens["refresh_token"] == "1//test_refresh_token"
            mock_save.assert_called_once()


def test_exchange_antigravity_code_failure():
    from monika.infrastructure.auth.antigravity_bridge import exchange_antigravity_code

    with patch("urllib.request.urlopen", side_effect=Exception("OAuth error")):
        tokens = exchange_antigravity_code("invalid_code", "test_verifier")
        assert tokens is None


def test_refresh_antigravity_token_success():
    from monika.infrastructure.auth.antigravity_bridge import refresh_antigravity_token

    mock_resp_data = json.dumps(
        {
            "access_token": "ya29.refreshed_access_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with patch("monika.infrastructure.auth.antigravity_bridge.save_oauth_tokens") as mock_save:
            tokens = refresh_antigravity_token("1//existing_refresh_token")
            assert tokens is not None
            assert tokens["access_token"] == "ya29.refreshed_access_token"
            assert tokens["refresh_token"] == "1//existing_refresh_token"
            mock_save.assert_called_once()


def test_refresh_antigravity_token_empty():
    from monika.infrastructure.auth.antigravity_bridge import refresh_antigravity_token

    assert refresh_antigravity_token("") is None


def test_resolve_antigravity_access_token_active():
    from monika.infrastructure.auth.antigravity_bridge import resolve_antigravity_access_token

    mock_record = {
        "access_token": "ya29.valid_token",
        "expires_at": 9999999999.0,
    }
    with patch("monika.infrastructure.auth.antigravity_bridge.get_oauth_tokens", return_value=mock_record):
        with patch("monika.infrastructure.auth.antigravity_bridge.is_token_expiring", return_value=False):
            token = resolve_antigravity_access_token()
            assert token == "ya29.valid_token"


def test_resolve_antigravity_access_token_expired():
    from monika.infrastructure.auth.antigravity_bridge import resolve_antigravity_access_token

    mock_record = {
        "access_token": "ya29.old_token",
        "refresh_token": "1//refresh_token",
        "expires_at": 100.0,
    }
    with patch("monika.infrastructure.auth.antigravity_bridge.get_oauth_tokens", return_value=mock_record):
        with patch("monika.infrastructure.auth.antigravity_bridge.is_token_expiring", return_value=True):
            with patch(
                "monika.infrastructure.auth.antigravity_bridge.refresh_antigravity_token",
                return_value={"access_token": "ya29.new_token"},
            ):
                token = resolve_antigravity_access_token()
                assert token == "ya29.new_token"


def test_oauth_callback_handler_get():
    import threading
    from monika.infrastructure.auth.antigravity_bridge import OAuthCallbackHandler

    ready_event = threading.Event()
    OAuthCallbackHandler.expected_state = "expected_state_123"
    OAuthCallbackHandler.captured_code = None
    OAuthCallbackHandler.captured_error = None
    OAuthCallbackHandler.ready = ready_event

    mock_request = MagicMock()
    mock_wfile = io.BytesIO()

    # Subclass handler without invoking server loop
    class TestHandler(OAuthCallbackHandler):
        def __init__(self, path):
            self.path = path
            self.wfile = mock_wfile
            self.rfile = io.BytesIO()
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    # 1. State mismatch
    h1 = TestHandler("/oauth2callback?state=wrong_state&code=test_code")
    h1.do_GET()
    assert h1.status_code == 400
    assert OAuthCallbackHandler.captured_error == "OAuth state mismatch."

    # 2. Success callback
    OAuthCallbackHandler.captured_error = None
    h2 = TestHandler("/oauth2callback?state=expected_state_123&code=4/0A_valid_code")
    h2.do_GET()
    assert h2.status_code == 200
    assert OAuthCallbackHandler.captured_code == "4/0A_valid_code"
    assert ready_event.is_set()
