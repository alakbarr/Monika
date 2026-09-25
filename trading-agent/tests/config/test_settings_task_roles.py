# ==============================================================================
# File: tests/config/test_settings_task_roles.py
# ==============================================================================

import pytest
import os
from config.settings import load_settings
from analysis.providers.llm_factory import LLMFactory
from analysis.providers.openrouter_provider import OPENROUTER_MODEL_ALIASES


def test_task_roles_uniform_routing():
    """Memastikan seluruh task_roles terdefinisi valid dengan primary dan fallbacks."""
    settings = load_settings()
    task_roles = settings.get("llm", {}).get("task_roles", {})
    assert len(task_roles) >= 25, f"Expected at least 25 task roles, got {len(task_roles)}"

    for role_name, role_cfg in task_roles.items():
        assert role_cfg.get("primary"), f"Role '{role_name}' must have a primary model"
        assert role_cfg.get("fallback_1"), f"Role '{role_name}' must have a fallback_1 model"


def test_all_task_role_models_exist_in_catalog():
    """Memastikan semua model di task_roles terdaftar di model_catalog."""
    settings = load_settings()
    catalog = settings.get("llm", {}).get("model_catalog", {})
    task_roles = settings.get("llm", {}).get("task_roles", {})

    for role_name, role_cfg in task_roles.items():
        for slot in ["primary", "fallback_1", "fallback_2", "fallback_3", "fallback_4", "fallback_5", "fallback_6", "fallback_7", "fallback_8"]:
            model = role_cfg.get(slot)
            if model:
                assert model in catalog, f"Role '{role_name}' slot '{slot}' model '{model}' not found in model_catalog"


def test_ai_price_benchmark_models_registered():
    """Memastikan model dari ai_price_benchmark.md terdaftar di model_catalog."""
    settings = load_settings()
    catalog = settings.get("llm", {}).get("model_catalog", {})

    expected_openrouter_models = [
        "fable-5", "claude-fable-5", "opus-5", "claude-opus-5", "opus-4.8", "opus-4.7", "opus-4.6", "opus-4.5",
        "sonnet-5", "claude-sonnet-5", "sonnet-4.6", "claude-sonnet-4.6", "sonnet-4.5", "claude-sonnet-4.5",
        "haiku-4.5", "claude-haiku-4.5",
        "deepseek-v4-pro", "deepseek-v4-pro-0813", "deepseek-v4-flash", "deepseek-v4-flash-0731",
        "glm-5.3", "glm-5.2", "glm-5.2:free", "glm-5.1",
        "gemini-3.1-pro-preview", "gemini-2.5-pro",
        "muse-spark-1.2", "minimax-m3", "kimi-k3",
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.5", "gpt-5.4", "gpt-5.6-luna", "gpt-5.4-mini", "gpt-5.4-nano",
        "qwen3.8-max", "qwen3.8-2.4t-a95b", "qwen3.8-27b",
        "grok-4.6", "grok-4.5", "grok-4.3",
        "mimo-v2.5-pro", "mimo-v2.5",
        "ox-alpha"
    ]

    for m in expected_openrouter_models:
        assert m in catalog, f"Model '{m}' should be in model_catalog"
        expected_provider = "groq" if m == "qwen3.8-27b" else "openrouter"
        assert catalog[m]["provider"] == expected_provider, f"Model '{m}' should have provider '{expected_provider}', got '{catalog[m]['provider']}'"

    expected_gemini_models = [
        "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
        "gemini-3.0-flash-preview", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"
    ]

    for m in expected_gemini_models:
        assert m in catalog, f"Gemini flash model '{m}' should be in model_catalog"
        assert catalog[m]["provider"] == "gemini", f"Gemini flash model '{m}' must stay on provider 'gemini', got '{catalog[m]['provider']}'"


def test_openrouter_aliases_registered():
    """Memastikan OPENROUTER_MODEL_ALIASES memetakan model-model utama."""
    assert OPENROUTER_MODEL_ALIASES.get("ox-alpha") == "stealth/ox-alpha"
    assert OPENROUTER_MODEL_ALIASES.get("glm-5.2") in ("z-ai/glm-5.2", "zhipu/glm-5.2")
    assert OPENROUTER_MODEL_ALIASES.get("glm-5.2:free") in ("z-ai/glm-5.2:free", "zhipu/glm-5.2:free")
    assert OPENROUTER_MODEL_ALIASES.get("glm-5.3") in ("z-ai/glm-5.3", "zhipu/glm-5.3")
    assert OPENROUTER_MODEL_ALIASES.get("glm-5.1") in ("z-ai/glm-5.1", "zhipu/glm-5.1")
    assert OPENROUTER_MODEL_ALIASES.get("kimi-k3") == "moonshot/kimi-k3"
    assert OPENROUTER_MODEL_ALIASES.get("minimax-m3") == "minimax/minimax-m3"
    assert OPENROUTER_MODEL_ALIASES.get("minimax/minimax-m3:free") == "minimax/minimax-m3:free"
    assert OPENROUTER_MODEL_ALIASES.get("qwen3.8-max") == "qwen/qwen3.8-max"
    assert OPENROUTER_MODEL_ALIASES.get("grok-4.6") == "x-ai/grok-4.6"
    assert OPENROUTER_MODEL_ALIASES.get("mimo-v2.5-pro") == "xiaomi/mimo-v2.5-pro"


def test_llm_factory_resolves_all_task_roles():
    """Memastikan LLMFactory dapat membuat client wrapper untuk setiap task role tanpa error."""
    settings = load_settings()
    factory = LLMFactory(settings)
    task_roles = settings.get("llm", {}).get("task_roles", {})

    for role_name in task_roles:
        client = factory.get_client_for_task(role_name)
        assert client is not None, f"Failed to instantiate client wrapper for task '{role_name}'"
        assert client.model is not None, f"Client model for '{role_name}' should not be None"
        assert hasattr(client, "fallbacks")


def test_openrouter_free_models_registered_in_catalog():
    """Memastikan seluruh model free tier OpenRouter baru terdaftar di model_catalog dengan cost_tier 'free'."""
    settings = load_settings()
    catalog = settings.get("llm", {}).get("model_catalog", {})

    expected_free_models = [
        "gemma-4-31b:free", "google/gemma-4-31b-it:free",
        "gemma-4-26b:free", "google/gemma-4-26b-a4b-it:free",
        "nemotron-3-ultra:free", "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nemotron-3.5-lightning:free", "nvidia/nemotron-3.5-lightning:free",
        "nemotron-3-super:free", "nvidia/nemotron-3-super-120b-a12b:free",
        "nemotron-3-nano:free", "nvidia/nemotron-3-nano-30b-a3b:free",
        "nemotron-3-nano-omni:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "nemotron-nano-12b-vl:free", "nvidia/nemotron-nano-12b-v2-vl:free",
        "nemotron-nano-9b:free", "nvidia/nemotron-nano-9b-v2:free",
        "nemotron-3.5-safety:free", "nvidia/nemotron-3.5-content-safety:free",
        "north-mini-code:free", "cohere/north-mini-code:free",
        "laguna-s-2.1:free", "poolside/laguna-s-2.1:free",
        "laguna-xs-2.1:free", "poolside/laguna-xs-2.1:free",
        "inkling:free", "thinkingmachines/inkling:free",
        "inkling-small:free", "thinkingmachines/inkling-small:free",
        "dots-3-note:free", "dots-studio/dots-3-note-preview:free",
        "lfm-2.5-2.6b:free", "liquid/lfm-2.5-2.6b:free",
        "openrouter/free"
    ]

    for model_name in expected_free_models:
        assert model_name in catalog, f"Model '{model_name}' must be registered in model_catalog"
        assert catalog[model_name]["provider"] == "openrouter", f"Model '{model_name}' provider should be openrouter"
        assert catalog[model_name]["cost_tier"] == "free", f"Model '{model_name}' cost_tier should be 'free'"


def test_summarizer_task_role_and_factory():
    """Memastikan role summarizer terkonfigurasi dengan max_tokens 2048 dan get_client_for_task berfungsi."""
    from analysis.providers.llm_factory import get_client_for_task
    settings = load_settings()
    task_roles = settings.get("llm", {}).get("task_roles", {})

    assert "summarizer" in task_roles, "Role 'summarizer' must be defined in settings.yaml"
    summarizer_cfg = task_roles["summarizer"]
    assert summarizer_cfg.get("max_tokens") == 2048, "summarizer max_tokens should be 2048"
    assert summarizer_cfg.get("primary") == "gemini-3.5-flash-lite"

    # Verifikasi get_client_for_task dengan explicit settings
    client_explicit = get_client_for_task("summarizer", settings)
    assert client_explicit is not None

    # Verifikasi get_client_for_task dengan default None settings
    client_default = get_client_for_task("summarizer")
    assert client_default is not None


