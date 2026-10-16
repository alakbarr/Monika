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
