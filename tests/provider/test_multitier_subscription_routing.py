# ==============================================================================
# File: tests/provider/test_multitier_subscription_routing.py
# ==============================================================================

"""
Unit tests for Monika Multi-Tier Subscription & Provider Routing.
Validates:
1. Provider prefix resolution for antigravity and opencode.
2. Model catalog alias mapping (remote_model / model_name translation).
3. ProviderRegistry _create_antigravity behavior with direct OAuth token vs proxy.
4. GeminiProvider OAuth Bearer token handling and Argon/Pro quota attribution.
"""

from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.llm.rate_limiting.gemini_rate_limiter import get_quota_for_model
from monika.infrastructure.providers.gemini_provider import GeminiProvider
from monika.infrastructure.providers.llm_factory import LLMFactory
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.infrastructure.providers.opencode_provider import OpenCodeProvider
from monika.infrastructure.providers.provider_registry import ProviderRegistry


def test_provider_prefix_resolution_opencode_and_antigravity():
    settings = {
        "llm": {
            "model_catalog": {},
            "providers": {
                "opencode": {"enabled": True},
                "antigravity": {"enabled": True},
                "openrouter": {"enabled": True},
            },
        }
    }
    factory = LLMFactory(settings)

    assert factory._resolve_provider("opencode:gemini-4-argon-contributor") == "opencode"
    assert factory._resolve_provider("opencode:deepseek-v4.1-flash") == "opencode"
    assert factory._resolve_provider("opencode_go:glm-5.3-flash") == "opencode_go"
    assert factory._resolve_provider("muse-spark-1.2-contributor") == "opencode"
    assert factory._resolve_provider("muse-spark-1.3-contributor") == "opencode"
    assert factory._resolve_provider("muse-spark-1.2-contributor-openrouter") == "openrouter"
    assert factory._resolve_provider("muse-spark-1.3-contributor-openrouter") == "openrouter"
    assert factory._resolve_provider("meta/muse-spark-1.2-contributor") == "openrouter"
    assert factory._resolve_provider("antigravity:gemini-4-argon") == "antigravity"
    assert factory._resolve_provider("agy:gemini-4-argon") == "agy"
    assert factory._resolve_provider("openrouter:google/gemini-4-argon") == "openrouter"


def test_model_catalog_alias_mapping():
    settings = {
        "llm": {
            "providers": {
                "opencode": {"enabled": True, "api_key": "test_opencode_key"},
                "openrouter": {"enabled": True, "api_key": "test_openrouter_key"},
            },
            "model_catalog": {
                "gemini-4-argon-opencode": {
                    "provider": "opencode",
                    "model_name": "gemini-4-argon-contributor",
                },
                "gemini-4-argon-openrouter": {
                    "provider": "openrouter",
                    "model_name": "google/gemini-4-argon",
                },
                "muse-spark-1.2-opencode": {
                    "provider": "opencode",
                    "model_name": "muse-spark-1.2-contributor",
                },
                "muse-spark-1.2-contributor-openrouter": {
                    "provider": "openrouter",
                    "model_name": "meta/muse-spark-1.2-contributor",
                },
            },
            "task_roles": {},
        }
    }
    factory = LLMFactory(settings)
    role_config = {"max_tokens": 4096, "temperature": 0.0}

    # Test OpenCode alias mapping
    client_oc = factory._create_client_instance("gemini-4-argon-opencode", role_config)
    assert isinstance(client_oc, OpenCodeProvider)
    assert client_oc.model == "gemini-4-argon-contributor"
    assert client_oc.provider_name == "opencode"

    # Test OpenRouter alias mapping
    client_or = factory._create_client_instance("gemini-4-argon-openrouter", role_config)
    assert client_or is not None
    assert client_or.model == "google/gemini-4-argon"

    # Test Muse Spark OpenCode alias mapping
    client_muse_oc = factory._create_client_instance("muse-spark-1.2-opencode", role_config)
    assert isinstance(client_muse_oc, OpenCodeProvider)
    assert client_muse_oc.model == "muse-spark-1.2-contributor"
    assert client_muse_oc.provider_name == "opencode"

    # Test Muse Spark OpenRouter Contributor alias mapping
    client_muse_or = factory._create_client_instance("muse-spark-1.2-contributor-openrouter", role_config)
    assert client_muse_or is not None
    assert client_muse_or.model == "meta/muse-spark-1.2-contributor"


def test_provider_registry_antigravity_direct_oauth_fallback():
    settings = {"llm": {"providers": {"gemini": {}}}}
    role_config = {"max_tokens": 8192, "temperature": 0.0}

    # Case 1: Local proxy is offline, but native Antigravity OAuth token is available
    with patch(
        "monika.infrastructure.auth.antigravity_bridge.check_antigravity_bridge_health",
        return_value={"running": False, "authenticated": False, "healthy": False},
    ):
        with patch(
            "monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token",
            return_value="ya29.a0AfH6SMTestOAuthToken",
        ):
            client = ProviderRegistry.create_client(
                provider_name="antigravity",
                model_name="gemini-4-argon",
                settings=settings,
                role_config=role_config,
            )
            assert isinstance(client, GeminiProvider)
            assert client.model == "gemini-4-argon"
            assert client.paid_api_key == "ya29.a0AfH6SMTestOAuthToken"

    # Case 2: Local proxy is online -> uses OpenAIProvider proxy
    with patch(
        "monika.infrastructure.auth.antigravity_bridge.check_antigravity_bridge_health",
        return_value={"running": True, "authenticated": True, "healthy": True},
    ):
        client_proxy = ProviderRegistry.create_client(
            provider_name="antigravity",
            model_name="gemini-4-argon",
            settings=settings,
            role_config=role_config,
        )
        assert isinstance(client_proxy, OpenAIProvider)
        assert client_proxy.model == "gemini-4-argon"
        assert client_proxy.provider_name == "antigravity"


def test_gemini_provider_oauth_bearer_auth():
    settings = {"llm": {"providers": {"gemini": {}}}}
    oauth_token = "ya29.a0AfH6SMTestMockAccessToken"

    with patch.dict("os.environ", {}, clear=True):
        provider = GeminiProvider(
            model="gemini-4-argon",
            api_key=oauth_token,
            settings=settings,
        )
        assert provider._is_paid_key(oauth_token) is True
        assert provider._get_api_key() == oauth_token


def test_gemini_provider_argon_auto_paid_key_resolution():
    settings = {"llm": {"providers": {"gemini": {}}}}
    oauth_token = "ya29.a0AfH6SMRefreshedToken"

    with patch("monika.core.security.credential_vault.vault.get_secret", return_value=None):
        with patch.dict("os.environ", {}, clear=True):
            with patch(
                "monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token",
                return_value=oauth_token,
            ):
                provider = GeminiProvider(
                    model="gemini-4-argon",
                    settings=settings,
                )
                assert provider.paid_api_key == oauth_token
                assert provider._get_api_key() == oauth_token


def test_gemini_rate_limiter_argon_and_free_keys():
    with patch.dict("os.environ", {"GEMINI_API_KEYS": "k1,k2,k3,k4,k5"}, clear=True):
        # 5 keys -> flash lite quota is 500 * 5 = 2500 RPD, 15 * 5 = 75 RPM
        lite_quota = get_quota_for_model("gemini-3.5-flash-lite")
        assert lite_quota["rpd"] == 2500
        assert lite_quota["rpm"] == 75

        # Argon is treated with pro quota (10000 RPD, 360 RPM)
        argon_quota = get_quota_for_model("gemini-4-argon")
        assert argon_quota["rpd"] == 10000
        assert argon_quota["rpm"] == 360
