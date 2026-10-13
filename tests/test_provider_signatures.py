import inspect
from monika.infrastructure.providers.base_provider import BaseLLMClient
from monika.infrastructure.providers.anthropic_provider import AnthropicProvider
from monika.infrastructure.providers.gemini_provider import GeminiProvider
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider
from monika.infrastructure.providers.deepseek_provider import DeepSeekProvider
from monika.infrastructure.providers.groq_provider import GroqProvider

from monika.infrastructure.providers.ollama_provider import OllamaProvider
from monika.infrastructure.providers.llm_factory import FallbackClientWrapper


def test_all_providers_accept_temperature_kwarg():
    """Setiap file di analysis/debate/*.py memanggil generate_content(...,
    temperature=X). Test ini mencegah regresi TypeError yang pernah
    membuat seluruh subsistem debate crash setiap cycle."""
    for provider_cls in [
        AnthropicProvider,
        GeminiProvider,
        OpenAIProvider,
        OpenRouterProvider,
        DeepSeekProvider,
        GroqProvider,
        OllamaProvider,
        FallbackClientWrapper,
    ]:
        sig = (
            inspect.signature(provider_cls.generate_content)
            if "generate_content" in provider_cls.__dict__
            else inspect.signature(BaseLLMClient.generate_content)
        )
        assert "temperature" in sig.parameters, (
            f"{provider_cls.__name__}.generate_content must accept temperature kwarg"
        )
        sig2 = inspect.signature(provider_cls.classify_json)
        assert "temperature" in sig2.parameters, f"{provider_cls.__name__}.classify_json must accept temperature kwarg"


def test_all_providers_classify_json_accepts_kwargs():
    """Memastikan semua provider memiliki parameter **kwargs pada classify_json
    sebagaimana didefinisikan pada BaseLLMClient.classify_json untuk mematuhi LSP
    dan mencegah reportIncompatibleMethodOverride."""
    for provider_cls in [
        AnthropicProvider,
        GeminiProvider,
        OpenAIProvider,
        OpenRouterProvider,
        DeepSeekProvider,
        GroqProvider,
        OllamaProvider,
        FallbackClientWrapper,
    ]:
        sig = inspect.signature(provider_cls.classify_json)
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        assert has_var_keyword, f"{provider_cls.__name__}.classify_json must accept **kwargs to match BaseLLMClient"


def test_all_providers_generate_content_accepts_kwargs():
    """Memastikan semua provider memiliki parameter **kwargs pada generate_content
    sebagaimana didefinisikan pada BaseLLMClient.generate_content untuk mematuhi LSP."""
    for provider_cls in [
        AnthropicProvider,
        GeminiProvider,
        OpenAIProvider,
        OpenRouterProvider,
        DeepSeekProvider,
        GroqProvider,
        OllamaProvider,
        FallbackClientWrapper,
    ]:
        sig = (
            inspect.signature(provider_cls.generate_content)
            if "generate_content" in provider_cls.__dict__
            else inspect.signature(BaseLLMClient.generate_content)
        )
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        assert has_var_keyword, f"{provider_cls.__name__}.generate_content must accept **kwargs to match BaseLLMClient"


def test_all_providers_generate_content_default_parameters():
    """Memastikan generate_content memiliki nilai default untuk system_prompt dan user_message
    sehingga tidak melanggar LSP saat dioverride."""
    for provider_cls in [
        AnthropicProvider,
        GeminiProvider,
        OpenAIProvider,
        OpenRouterProvider,
        DeepSeekProvider,
        GroqProvider,
        OllamaProvider,
        FallbackClientWrapper,
    ]:
        sig = (
            inspect.signature(provider_cls.generate_content)
            if "generate_content" in provider_cls.__dict__
            else inspect.signature(BaseLLMClient.generate_content)
        )
        if "system_prompt" in sig.parameters:
            assert sig.parameters["system_prompt"].default != inspect.Parameter.empty, (
                f"{provider_cls.__name__}.generate_content system_prompt must have a default value"
            )
        if "user_message" in sig.parameters:
            assert sig.parameters["user_message"].default != inspect.Parameter.empty, (
                f"{provider_cls.__name__}.generate_content user_message must have a default value"
            )


def test_all_providers_generate_signature_compatibility():
    """Memastikan semua provider memiliki parameter standar pada generate():
    prompt, system, temperature, max_tokens, dan **kwargs."""
    for provider_cls in [
        AnthropicProvider,
        GeminiProvider,
        OpenAIProvider,
        OpenRouterProvider,
        DeepSeekProvider,
        GroqProvider,
        OllamaProvider,
        FallbackClientWrapper,
    ]:
        sig = (
            inspect.signature(provider_cls.generate)
            if "generate" in provider_cls.__dict__
            else inspect.signature(BaseLLMClient.generate)
        )
        for param in ["prompt", "system", "temperature", "max_tokens"]:
            assert param in sig.parameters, f"{provider_cls.__name__}.generate must accept parameter {param}"
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        assert has_var_keyword, f"{provider_cls.__name__}.generate must accept **kwargs"
