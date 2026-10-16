# ==============================================================================
# File: tests/provider/test_zai_provider.py
# ==============================================================================

"""
Unit tests for Z.AI / GLM Provider.
"""

from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.providers.zai_provider import DEFAULT_ZAI_BASE_URL, ZAIProvider


def test_zai_provider_init_with_key():
    with patch("monika.core.security.credential_vault.vault.get_secret", return_value="zai-mock-key"):
        provider = ZAIProvider(model="glm-4-flash")
        assert provider.api_key == "zai-mock-key"
        assert provider.base_url == DEFAULT_ZAI_BASE_URL
        assert provider.provider_name == "zai"


def test_zai_provider_init_without_key():
    with patch("monika.core.security.credential_vault.vault.get_secret", return_value=None):
        with patch.dict("os.environ", {}, clear=True):
            provider = ZAIProvider(model="glm-4-flash")
            assert provider.api_key is None
            assert provider.client is None


def test_zai_provider_apply_reasoning_params_thinking_enabled():
    provider = ZAIProvider(model="glm-4-plus", api_key="test-key", thinking_level="high")
    kwargs = {}
    provider._apply_reasoning_params(kwargs)
    assert kwargs.get("extra_body") == {"thinking": True}
    assert kwargs.get("reasoning_effort") == "high"


def test_zai_provider_apply_reasoning_params_thinking_disabled():
    provider = ZAIProvider(model="glm-4-flash", api_key="test-key", thinking_level="none")
    kwargs = {}
    provider._apply_reasoning_params(kwargs)
    assert kwargs.get("extra_body") == {"thinking": False}
    assert "reasoning_effort" not in kwargs
