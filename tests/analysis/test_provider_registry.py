# ==============================================================================
# File: tests/analysis/test_provider_registry.py
# ==============================================================================

import pytest
from unittest.mock import MagicMock
from analysis.providers.provider_registry import ProviderRegistry, LLMProviderPlugin
from harness.contract import PluginCategory, PluginMetadata


def test_provider_registry_builtins():
    providers = ProviderRegistry.list_providers()
    assert "anthropic" in providers
    assert "gemini" in providers
    assert "openai" in providers
    assert "deepseek" in providers
    assert "ollama" in providers
    assert "groq" in providers
    assert "openrouter" in providers
    assert "typesafe" in providers
    assert "openai_compatible" in providers


def test_provider_registry_custom_plugin():
    class CustomProviderPlugin(LLMProviderPlugin):
        metadata = PluginMetadata(
            id="custom-llm",
            name="Custom LLM Plugin",
            version="1.0.0",
            category=PluginCategory.LLM_PROVIDER,
        )

        def create_client(self, model_name, settings, role_config, task_role="default", **kwargs):
            mock_client = MagicMock()
            mock_client.model = model_name
            mock_client.role = task_role
            return mock_client

    plugin = CustomProviderPlugin()
    assert plugin.metadata.category == PluginCategory.LLM_PROVIDER

    ProviderRegistry.register("custom-llm", plugin)
    client = ProviderRegistry.create_client(
        provider_name="custom-llm",
        model_name="custom-model-v1",
        settings={},
        role_config={},
        task_role="test_role",
    )
    assert client is not None
    assert client.model == "custom-model-v1"
    assert client.role == "test_role"


def test_provider_registry_unknown_returns_none():
    client = ProviderRegistry.create_client(
        provider_name="non_existent_provider_xyz",
        model_name="foo",
        settings={},
        role_config={},
    )
    assert client is None
