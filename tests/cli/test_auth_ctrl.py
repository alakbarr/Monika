# ==============================================================================
# File: tests/cli/test_auth_ctrl.py
# ==============================================================================

"""
Unit tests for CLI Authentication Controller.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from monika.interfaces.cli.commands.auth_ctrl import (
    handle_auth_command,
    login_provider,
    logout_provider,
    show_auth_status,
)


def test_show_auth_status_runs_cleanly():
    with patch(
        "monika.interfaces.cli.commands.auth_ctrl.check_antigravity_bridge_health",
        return_value={"running": False, "authenticated": False, "message": "Bridge offline"},
    ):
        with patch("monika.interfaces.cli.commands.auth_ctrl.is_antigravity_installed", return_value=True):
            code = show_auth_status()
            assert code == 0


def test_handle_auth_command_status():
    args = SimpleNamespace(auth_action="status")
    with patch("monika.interfaces.cli.commands.auth_ctrl.show_auth_status", return_value=0) as mock_status:
        code = handle_auth_command(args)
        assert code == 0
        mock_status.assert_called_once()


def test_handle_auth_command_login():
    args = SimpleNamespace(auth_action="login", provider="invalid_prov")
    code = handle_auth_command(args)
    assert code == 1


def test_logout_provider_success():
    with patch("monika.interfaces.cli.commands.auth_ctrl.delete_oauth_tokens") as mock_delete:
        with patch("monika.interfaces.cli.commands.auth_ctrl.vault.delete_secret") as mock_vault_del:
            code = logout_provider("zai")
            assert code == 0
            mock_delete.assert_called_once_with("zai")
            mock_vault_del.assert_called_once_with("ZAI_API_KEY")


def test_logout_provider_invalid():
    code = logout_provider("unknown_prov")
    assert code == 1


def test_show_auth_status_with_antigravity_oauth():
    mock_record = {
        "access_token": "ya29.test_access_token",
        "expires_at": 9999999999.0,
        "source": "google_antigravity_oauth",
    }
    with patch(
        "monika.interfaces.cli.commands.auth_ctrl.get_oauth_tokens",
        side_effect=lambda p: mock_record if p == "antigravity" else None,
    ):
        with patch(
            "monika.interfaces.cli.commands.auth_ctrl.check_antigravity_bridge_health", return_value={"running": False}
        ):
            with patch("monika.interfaces.cli.commands.auth_ctrl.is_antigravity_installed", return_value=True):
                code = show_auth_status()
                assert code == 0


def test_login_antigravity_existing_retained():
    mock_record = {
        "access_token": "ya29.existing",
        "expires_at": 9999999999.0,
    }
    with patch("monika.interfaces.cli.commands.auth_ctrl.get_oauth_tokens", return_value=mock_record):
        with patch("builtins.input", return_value="n"):
            code = login_provider("antigravity")
            assert code == 0


def test_login_antigravity_callback_success():
    with patch("monika.interfaces.cli.commands.auth_ctrl.get_oauth_tokens", return_value=None):
        with patch(
            "monika.interfaces.cli.commands.auth_ctrl.generate_antigravity_pkce",
            return_value=("test_verifier", "test_challenge"),
        ):
            with patch("monika.interfaces.cli.commands.auth_ctrl.webbrowser.open"):
                with patch(
                    "monika.interfaces.cli.commands.auth_ctrl.exchange_antigravity_code",
                    return_value={"access_token": "ya29.token"},
                ):
                    with patch("http.server.HTTPServer"):
                        # Simulate ready_event fired with captured code
                        from monika.interfaces.cli.commands.auth_ctrl import OAuthCallbackHandler

                        def mock_wait(timeout=None):
                            OAuthCallbackHandler.captured_code = "4/0A_test_code"
                            OAuthCallbackHandler.captured_error = None
                            return True

                        with patch("threading.Event.wait", side_effect=mock_wait):
                            code = login_provider("antigravity")
                            assert code == 0


def test_logout_provider_antigravity():
    with patch("monika.interfaces.cli.commands.auth_ctrl.delete_oauth_tokens") as mock_delete:
        code = logout_provider("antigravity")
        assert code == 0
        mock_delete.assert_called_once_with("antigravity")

    with patch("monika.interfaces.cli.commands.auth_ctrl.delete_oauth_tokens") as mock_delete:
        code = logout_provider("gemini")
        assert code == 0
        mock_delete.assert_called_once_with("antigravity")
