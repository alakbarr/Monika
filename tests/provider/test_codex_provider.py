# ==============================================================================
# File: tests/provider/test_codex_provider.py
# ==============================================================================

"""
Unit tests for OpenAI Codex Provider.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.infrastructure.providers.codex_provider import CodexProvider


def test_codex_provider_init_with_token():
    with patch(
        "monika.infrastructure.providers.codex_provider.resolve_codex_access_token", return_value="mock-token-123"
    ):
        provider = CodexProvider(model="gpt-4o")
        assert provider.api_key == "mock-token-123"
        assert provider.provider_name == "codex"


def test_codex_provider_init_without_token():
    with patch("monika.infrastructure.providers.codex_provider.resolve_codex_access_token", return_value=None):
        with patch.dict("os.environ", {}, clear=True):
            provider = CodexProvider(model="gpt-4o")
            assert provider.api_key is None
            assert provider.client is None


def test_codex_provider_ensure_active_token_refreshes():
    with patch("monika.infrastructure.providers.codex_provider.resolve_codex_access_token", return_value="old-token"):
        provider = CodexProvider(model="gpt-4o")
        assert provider.api_key == "old-token"

    # Now token refreshes
    with patch(
        "monika.infrastructure.providers.codex_provider.resolve_codex_access_token", return_value="refreshed-token"
    ):
        has_token = provider._ensure_active_token()
        assert has_token is True
        assert provider.api_key == "refreshed-token"
        if provider.client:
            assert provider.client.api_key == "refreshed-token"
