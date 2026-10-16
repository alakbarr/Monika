# ==============================================================================
# File: tests/auth/test_codex_device_flow.py
# ==============================================================================

"""
Unit tests for OpenAI Codex Device Code Authorization and Token Refresh.
"""

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.auth.codex_device_flow import (
    CODEX_OAUTH_CLIENT_ID,
    exchange_codex_code,
    poll_codex_authorization,
    read_codex_cli_credentials,
    refresh_codex_token,
    request_codex_device_code,
)


def test_read_codex_cli_credentials(tmp_path):
    mock_codex_dir = tmp_path / ".codex"
    mock_codex_dir.mkdir(parents=True)
    auth_file = mock_codex_dir / "auth.json"
    data = {
        "tokens": {
            "access_token": "mock-codex-access-tok",
            "refresh_token": "mock-codex-refresh-tok",
            "account_id": "org-test-123",
        }
    }
    auth_file.write_text(json.dumps(data), encoding="utf-8")

    with patch("monika.infrastructure.auth.codex_device_flow.get_codex_cli_auth_path", return_value=auth_file):
        creds = read_codex_cli_credentials()
        assert creds is not None
        assert creds["access_token"] == "mock-codex-access-tok"
        assert creds["refresh_token"] == "mock-codex-refresh-tok"
        assert creds["account_id"] == "org-test-123"
        assert creds["source"] == "codex_cli_file"


def test_request_codex_device_code_success():
    mock_response = io.BytesIO(
        json.dumps(
            {
                "device_auth_id": "dev_auth_999",
                "user_code": "ABCD-1234",
                "interval": 2,
            }
        ).encode("utf-8")
    )
    mock_resp_obj = MagicMock()
    mock_resp_obj.read.side_effect = mock_response.read
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        resp = request_codex_device_code()
        assert resp["device_auth_id"] == "dev_auth_999"
        assert resp["user_code"] == "ABCD-1234"
        assert resp["interval"] == 3


def test_poll_codex_authorization_success():
    mock_response = io.BytesIO(
        json.dumps(
            {
                "authorization_code": "auth_code_xyz",
                "code_verifier": "verifier_123",
            }
        ).encode("utf-8")
    )
    mock_resp_obj = MagicMock()
    mock_resp_obj.status = 200
    mock_resp_obj.read.side_effect = mock_response.read
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        resp = poll_codex_authorization("dev_auth_999", "ABCD-1234", poll_interval=0.01, timeout=5)
        assert resp["authorization_code"] == "auth_code_xyz"


def test_exchange_codex_code_success():
    mock_response = io.BytesIO(
        json.dumps(
            {
                "access_token": "codex-access-tok-abc",
                "refresh_token": "codex-refresh-tok-def",
                "expires_in": 3600,
            }
        ).encode("utf-8")
    )
    mock_resp_obj = MagicMock()
    mock_resp_obj.read.side_effect = mock_response.read
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        with patch("monika.infrastructure.auth.codex_device_flow.save_oauth_tokens") as mock_save:
            tokens = exchange_codex_code({"authorization_code": "auth_code_xyz", "code_verifier": "verifier_123"})
            assert tokens is not None
            assert tokens["access_token"] == "codex-access-tok-abc"
            mock_save.assert_called_once()


def test_refresh_codex_token_success():
    existing_tokens = {
        "access_token": "expired-codex-tok",
        "refresh_token": "refresh-codex-tok",
    }
    mock_response = io.BytesIO(
        json.dumps(
            {
                "access_token": "new-codex-tok",
                "expires_in": 3600,
            }
        ).encode("utf-8")
    )
    mock_resp_obj = MagicMock()
    mock_resp_obj.read.side_effect = mock_response.read
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        with patch("monika.infrastructure.auth.codex_device_flow.save_oauth_tokens") as mock_save:
            refreshed = refresh_codex_token(existing_tokens)
            assert refreshed is not None
            assert refreshed["access_token"] == "new-codex-tok"
            assert refreshed["refresh_token"] == "refresh-codex-tok"
            mock_save.assert_called_once()
