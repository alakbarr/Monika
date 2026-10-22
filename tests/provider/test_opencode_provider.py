# ==============================================================================
# File: tests/provider/test_opencode_provider.py
# ==============================================================================

"""
Unit tests for OpenCode Go / Zen Provider.
"""

from unittest.mock import patch

from monika.infrastructure.providers.opencode_provider import (
    DEFAULT_OPENCODE_BASE_URL,
    OpenCodeProvider,
)
from monika.infrastructure.providers.provider_registry import ProviderRegistry


def test_opencode_provider_init_with_key():
    with patch("monika.core.security.credential_vault.vault.get_secret", return_value="oc_sk_mock_key"):
        provider = OpenCodeProvider(model="opencode-go/deepseek-v3")
        assert provider.api_key == "oc_sk_mock_key"
        assert provider.base_url == DEFAULT_OPENCODE_BASE_URL
        assert provider.provider_name == "opencode"


def test_opencode_provider_init_without_key():
    with patch("monika.core.security.credential_vault.vault.get_secret", return_value=None):
        with patch.dict("os.environ", {}, clear=True):
            provider = OpenCodeProvider(model="opencode-go/deepseek-v3")
            assert provider.api_key is None
            assert provider.client is None


def test_opencode_provider_custom_base_url():
    provider = OpenCodeProvider(
        model="opencode-go/glm-5",
        api_key="oc_sk_custom",
        base_url="https://custom.opencode.proxy/v1/",
    )
    assert provider.base_url == "https://custom.opencode.proxy/v1"


def test_opencode_provider_apply_reasoning_params():
    provider = OpenCodeProvider(
        model="opencode-go/deepseek-r1",
        api_key="oc_sk_test",
        thinking_level="high",
    )
    kwargs = {}
    provider._apply_reasoning_params(kwargs)
    assert kwargs.get("reasoning_effort") == "high"
    assert kwargs.get("extra_body") == {"thinking": True}


def test_opencode_provider_muse_spark_reasoning_pops_temperature():
    provider = OpenCodeProvider(
        model="muse-spark-1.2-contributor",
        api_key="oc_sk_test",
        thinking_level="high",
    )
    kwargs = {"temperature": 0.0, "max_tokens": 4096}
    provider._apply_reasoning_params(kwargs)
    assert "temperature" not in kwargs
    assert kwargs.get("reasoning_effort") == "high"
    assert kwargs.get("extra_body") == {"thinking": True}


def test_opencode_provider_effort_mapping_max_to_high():
    provider = OpenCodeProvider(
        model="muse-spark-1.3-contributor",
        api_key="oc_sk_test",
        thinking_level="max",
    )
    kwargs = {"temperature": 0.2}
    provider._apply_reasoning_params(kwargs)
    assert "temperature" not in kwargs
    assert kwargs.get("reasoning_effort") == "high"
    assert kwargs.get("extra_body") == {"thinking": True}


def test_opencode_registered_in_provider_registry():
    assert ProviderRegistry.get("opencode") is not None
    assert ProviderRegistry.get("opencode_go") is not None
    assert ProviderRegistry.get("opencode-go") is not None
