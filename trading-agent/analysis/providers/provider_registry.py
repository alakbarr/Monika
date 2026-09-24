# ==============================================================================
# File: analysis/providers/provider_registry.py
# ==============================================================================

"""
Pluggable LLM Provider Registry & Plugin Specification (Phase 3b).
Decouples LLM client creation from hardcoded if/elif chains into dynamic provider plugins.
"""

from abc import ABC, abstractmethod
import logging
from typing import Dict, Any, Optional, List, Callable

from harness.contract import TradingPlugin, PluginCategory, PluginMetadata

logger = logging.getLogger("TradingAgent.ProviderRegistry")


class LLMProviderPlugin(TradingPlugin, ABC):
    """
    Base contract for all LLM Provider Plugins in Monika.
    Allows external plugins to introduce custom LLM backends (e.g. Bedrock, Mistral, Vertex).
    """
    metadata: PluginMetadata

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "metadata"):
            self.metadata.category = PluginCategory.LLM_PROVIDER

    @abstractmethod
    def create_client(
        self,
        model_name: str,
        settings: dict,
        role_config: dict,
        task_role: str = "default",
        **kwargs
    ) -> Any:
        """Create and configure a provider client instance."""
        pass


class ProviderRegistry:
    """
    Central registry for LLM providers and provider plugins.
    Replaces monolithic if/elif cascades in LLMFactory with dynamic resolution.
    """
    _providers: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, provider_or_factory: Any) -> None:
        """Register an LLM provider plugin or factory callable."""
        key = name.lower().strip()
        cls._providers[key] = provider_or_factory
        logger.info(f"[ProviderRegistry] Registered LLM provider: {key}")

    @classmethod
    def get(cls, name: str) -> Optional[Any]:
        """Get registered provider by name."""
        return cls._providers.get(name.lower().strip())

    @classmethod
    def list_providers(cls) -> List[str]:
        """List all registered provider keys."""
        return sorted(list(cls._providers.keys()))

    @classmethod
    def create_client(
        cls,
        provider_name: str,
        model_name: str,
        settings: dict,
        role_config: dict,
        task_role: str = "default",
        **kwargs
    ) -> Optional[Any]:
        """
        Dynamically instantiate an LLM client through the registered provider.
        """
        key = provider_name.lower().strip()
        provider = cls.get(key)
        if not provider:
            logger.error(f"[ProviderRegistry] Provider '{provider_name}' not implemented or registered.")
            return None

        # If it's an LLMProviderPlugin instance
        if hasattr(provider, "create_client"):
            return provider.create_client(
                model_name=model_name,
                settings=settings,
                role_config=role_config,
                task_role=task_role,
                **kwargs
            )
        # If it's a factory callable
        if callable(provider):
            return provider(
                model_name=model_name,
                settings=settings,
                role_config=role_config,
                task_role=task_role,
                **kwargs
            )

        logger.error(f"[ProviderRegistry] Registered provider for '{key}' is neither a plugin nor callable.")
        return None

    @classmethod
    def reset(cls) -> None:
        """Clear all registered providers (primarily for unit tests)."""
        cls._providers.clear()
        _register_builtins()


def _register_builtins():
    """Register Monika's built-in LLM providers."""

    def _create_anthropic(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.anthropic_provider import AnthropicProvider
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return AnthropicProvider(
            model_name, max_tokens, max_tool_turns, thinking_level, settings, temperature, role=task_role, **key_kwargs
        )

    def _create_gemini(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.gemini_provider import GeminiProvider
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        pooled_key = kwargs.get("api_key")
        key_kwargs = {"api_key": pooled_key} if pooled_key else {}
        client = GeminiProvider(
            model_name, max_tokens, max_tool_turns, thinking_level, settings, temperature, role=task_role, **key_kwargs
        )
        if pooled_key and hasattr(client, "api_key"):
            setattr(client, "api_key", pooled_key)
        return client

    def _create_openai(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.openai_provider import OpenAIProvider
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return OpenAIProvider(
            model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
            thinking_level=thinking_level, settings=settings, temperature=temperature, role=task_role,
            **key_kwargs
        )

    def _create_deepseek(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.deepseek_provider import DeepSeekProvider
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return DeepSeekProvider(
            model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
            thinking_level=thinking_level, settings=settings, temperature=temperature, role=task_role,
            **key_kwargs
        )

    def _create_ollama(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.ollama_provider import OllamaProvider
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        thinking_level = kwargs.get("thinking_level", "none")
        return OllamaProvider(
            model_name, settings, max_tokens=max_tokens,
            max_tool_turns=max_tool_turns, thinking_level=thinking_level, role=task_role
        )

    def _create_groq(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.groq_provider import GroqProvider
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return GroqProvider(
            model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
            thinking_level=thinking_level, settings=settings, temperature=temperature, role=task_role,
            **key_kwargs
        )

    def _create_openrouter(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.openrouter_provider import OpenRouterProvider
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return OpenRouterProvider(
            model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
            thinking_level=thinking_level, settings=settings,
            temperature=temperature, role=task_role,
            **key_kwargs
        )

    def _create_typesafe(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.typesafe_provider import TypeSafeProvider
        provider_config = kwargs.get("provider_config", {})
        base_url = provider_config.get("base_url", "https://api.typesafe.ai")
        confidence_thresh = float(role_config.get("confidence_threshold", 0.70))
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return TypeSafeProvider(
            model=model_name,
            max_tokens=max_tokens,
            max_tool_turns=max_tool_turns,
            thinking_level="none",
            settings=settings,
            temperature=temperature,
            base_url=base_url,
            confidence_threshold=confidence_thresh,
            role=task_role,
            **key_kwargs
        )

    def _create_openai_compatible(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.openai_provider import OpenAIProvider
        provider_config = kwargs.get("provider_config", {})
        base_url = provider_config.get("base_url", "http://localhost:8000/v1")
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return OpenAIProvider(
            model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
            thinking_level=thinking_level, settings=settings,
            temperature=temperature, base_url=base_url, role=task_role,
            **key_kwargs
        )

    def _create_9router(model_name, settings, role_config, task_role="default", **kwargs):
        from analysis.providers.nine_router_provider import NineRouterProvider
        provider_config = kwargs.get("provider_config", {})
        base_url = provider_config.get("base_url") or kwargs.get("base_url")
        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        thinking_level = kwargs.get("thinking_level", "none")
        key_kwargs = {"api_key": kwargs.get("api_key")} if kwargs.get("api_key") else {}
        return NineRouterProvider(
            model=model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
            thinking_level=thinking_level, settings=settings,
            temperature=temperature, base_url=base_url, role=task_role,
            **key_kwargs
        )

    ProviderRegistry.register("anthropic", _create_anthropic)
    ProviderRegistry.register("gemini", _create_gemini)
    ProviderRegistry.register("openai", _create_openai)
    ProviderRegistry.register("deepseek", _create_deepseek)
    ProviderRegistry.register("ollama", _create_ollama)
    ProviderRegistry.register("groq", _create_groq)
    ProviderRegistry.register("openrouter", _create_openrouter)
    ProviderRegistry.register("typesafe", _create_typesafe)
    ProviderRegistry.register("openai_compatible", _create_openai_compatible)
    ProviderRegistry.register("9router", _create_9router)
    ProviderRegistry.register("ninerouter", _create_9router)
    ProviderRegistry.register("nine_router", _create_9router)


_register_builtins()
