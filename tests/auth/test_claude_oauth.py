# ==============================================================================
# File: tests/auth/test_claude_oauth.py
# ==============================================================================

"""
Unit tests for Claude Code OAuth Flow and Token Refresh.
"""

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.auth.claude_oauth import (
    CLAUDE_OAUTH_CLIENT_ID,
    exchange_code_for_token,
    generate_pkce_pair,
    get_claude_authorization_url,
    read_claude_code_credentials,
    refresh_claude_token,
)


def test_generate_pkce_pair():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) > 0
    assert verifier != challenge
    # Base64 URL safe characters only
    assert "=" not in challenge


def test_get_claude_authorization_url():
    verifier, challenge = generate_pkce_pair()
    url = get_claude_authorization_url(challenge, state="test_state_123")
    assert "console.anthropic.com/oauth/authorize" in url
    assert f"client_id={CLAUDE_OAUTH_CLIENT_ID}" in url
    assert f"code_challenge={challenge}" in url
    assert "code_challenge_method=S256" in url
    assert "state=test_state_123" in url


def test_read_claude_code_credentials_from_file(tmp_path):
    mock_creds_dir = tmp_path / ".claude"
    mock_creds_dir.mkdir(parents=True)
    creds_file = mock_creds_dir / ".credentials.json"
    data = {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oauth-token-test",
            "refreshToken": "sk-ant-refresh-test",
            "expiresAt": 1800000000,
        }
    }
    creds_file.write_text(json.dumps(data), encoding="utf-8")

    with patch("monika.infrastructure.auth.claude_oauth.get_claude_credentials_path", return_value=creds_file):
        creds = read_claude_code_credentials()
        assert creds is not None
        assert creds["access_token"] == "sk-ant-oauth-token-test"
        assert creds["refresh_token"] == "sk-ant-refresh-test"
        assert creds["expires_at"] == 1800000000
        assert creds["source"] == "claude_code_file"


def test_read_claude_code_credentials_missing():
    with patch(
        "monika.infrastructure.auth.claude_oauth.get_claude_credentials_path",
        return_value=Path("/nonexistent/path/creds.json"),
    ):
        with patch("monika.infrastructure.auth.claude_oauth.read_claude_code_keychain", return_value=None):
            creds = read_claude_code_credentials()
            assert creds is None


def test_exchange_code_for_token_success():
    mock_response = io.BytesIO(
        json.dumps(
            {
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        ).encode("utf-8")
    )
    mock_resp_obj = MagicMock()
    mock_resp_obj.read.side_effect = mock_response.read
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        with patch("monika.infrastructure.auth.claude_oauth.save_oauth_tokens") as mock_save:
            tokens = exchange_code_for_token("test-code", "test-verifier")
            assert tokens is not None
            assert tokens["access_token"] == "mock-access-token"
            mock_save.assert_called_once()


def test_refresh_claude_token_success():
    existing_tokens = {
        "access_token": "old-token",
        "refresh_token": "mock-refresh-token",
    }
    mock_response = io.BytesIO(
        json.dumps(
            {
                "access_token": "refreshed-token",
                "expires_in": 7200,
            }
        ).encode("utf-8")
    )
    mock_resp_obj = MagicMock()
    mock_resp_obj.read.side_effect = mock_response.read
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        with patch("monika.infrastructure.auth.claude_oauth.save_oauth_tokens") as mock_save:
            new_tokens = refresh_claude_token(existing_tokens)
            assert new_tokens is not None
            assert new_tokens["access_token"] == "refreshed-token"
            # Preserves refresh token if not returned
            assert new_tokens["refresh_token"] == "mock-refresh-token"
            mock_save.assert_called_once()
