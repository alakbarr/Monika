"""
Unit tests for caching threshold constants, model capabilities,
OpenRouter sticky routing, profile applicator roles, and OpenAI sub-task prompt_cache_key.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.core.config.profile_applicator import ALL_TASK_ROLES
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager
from monika.infrastructure.providers.capabilities import (
    MODEL_CAPABILITIES,
    get_model_capabilities,
)
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider


def test_breakpoint_constants() -> None:
    """Verify Gemini threshold constants are updated to >=4,096 * 1.15 tokens."""
    assert CacheBreakpointManager.GEMINI_3_MIN_CACHEABLE_CHARS == 21000
    assert CacheBreakpointManager.GEMINI_25_MIN_CACHEABLE_CHARS == 10500
    assert CacheBreakpointManager.get_min_cacheable_chars("gemini-3.8-flash") == 21000
    assert CacheBreakpointManager.get_min_cacheable_chars("gemini-2.5-flash") == 10500


def test_capabilities_resolution() -> None:
    """Verify capabilities for glm-5.3-flash, free tier, and explicit canonical entries."""
    assert get_model_capabilities("glm-5.3-flash").supports_caching is True
    assert get_model_capabilities("openrouter/free").supports_caching is False
    assert get_model_capabilities("free").supports_caching is False
    assert MODEL_CAPABILITIES["free"].supports_caching is False

    # Canonical entries present in MODEL_CAPABILITIES
    assert "deepseek-v4.1-flash-1017" in MODEL_CAPABILITIES
    assert MODEL_CAPABILITIES["deepseek-v4.1-flash-1017"].supports_caching is True

    assert "gemini-2.5-flash-lite" in MODEL_CAPABILITIES
    assert MODEL_CAPABILITIES["gemini-2.5-flash-lite"].supports_caching is True

    assert "gemini-3-flash-preview" in MODEL_CAPABILITIES
    assert MODEL_CAPABILITIES["gemini-3-flash-preview"].supports_caching is True


def test_openrouter_provider_order_derivation() -> None:
    """Verify OpenRouter sticky provider order derivation across model families."""
    # GLM / Z-AI
    prov_glm = OpenRouterProvider(model="z-ai/glm-5.3-flash", api_key="sk-or-test")
    kw_glm: dict = {}
    prov_glm._apply_provider_routing(kw_glm)
    prov_dict = kw_glm["extra_body"]["provider"]
    assert prov_dict["order"] == ["Zhipu", "DeepInfra", "Together"]
    assert prov_dict["allow_fallbacks"] is True

    # MiniMax
    prov_minimax = OpenRouterProvider(model="minimax/minimax-m3.1-flash", api_key="sk-or-test")
    kw_minimax: dict = {}
    prov_minimax._apply_provider_routing(kw_minimax)
    prov_dict = kw_minimax["extra_body"]["provider"]
    assert prov_dict["order"] == ["MiniMax", "Together"]
    assert prov_dict["allow_fallbacks"] is True

    # Gemini / Google
    prov_gemini = OpenRouterProvider(model="google/gemini-2.5-flash", api_key="sk-or-test")
    kw_gemini: dict = {}
    prov_gemini._apply_provider_routing(kw_gemini)
    prov_dict = kw_gemini["extra_body"]["provider"]
    assert prov_dict["order"] == ["Google", "Google AI Studio"]
    assert prov_dict["allow_fallbacks"] is True

    # DeepSeek
    prov_deepseek = OpenRouterProvider(model="deepseek/deepseek-chat", api_key="sk-or-test")
    kw_deepseek: dict = {}
    prov_deepseek._apply_provider_routing(kw_deepseek)
    prov_dict = kw_deepseek["extra_body"]["provider"]
    assert prov_dict["order"] == ["DeepSeek", "Together", "Fireworks", "DeepInfra"]
    assert prov_dict["allow_fallbacks"] is True


def test_strategy_discovery_presence_in_all_task_roles() -> None:
    """Verify strategy_discovery is preserved in ALL_TASK_ROLES."""
    assert "strategy_discovery" in ALL_TASK_ROLES


@pytest.mark.asyncio
async def test_openai_provider_prompt_cache_key_sub_task() -> None:
    """Verify prompt_cache_key derivation when sub_task is passed via attribute or kwargs."""
    provider = OpenAIProvider(model="gpt-4o", api_key="sk-test", settings={})
    provider.role = "stage2_per_asset_secondary"
    provider.sub_task = "second_opinion"

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    provider.client = mock_client

    # Case 1: sub_task on self
    kwargs1 = {"messages": []}
    await provider._create_chat_completion(kwargs1)
    assert kwargs1.get("prompt_cache_key") == "monika_stage2_per_asset_secondary:second_opinion"

    # Case 2: sub_task passed in kwargs
    provider.sub_task = None
    kwargs2 = {"messages": [], "sub_task": "second_opinion"}
    await provider._create_chat_completion(kwargs2)
    assert kwargs2.get("prompt_cache_key") == "monika_stage2_per_asset_secondary:second_opinion"
    assert "sub_task" not in kwargs2  # Sanitized so OpenAI SDK won't reject it
