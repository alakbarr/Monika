"""
Declarative model capability table for multi-provider LLM integration (Phase 6).
Maps provider-specific capabilities, token limits, and prompt caching strategies.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ModelCapabilities:
    """Declared operational capabilities for an LLM."""
    supports_tool_choice: bool = True
    supports_json_mode: bool = True
    supports_structured_output: bool = True
    supports_streaming: bool = True
    requires_reasoning_roundtrip: bool = False
    requires_reasoning_split: bool = False
    max_output_tokens: int = 8192
    context_window: int = 200000
    prompt_cache_strategy: str = "none"
    # Supported: "none", "anthropic_system_and_3", "deepseek_prefix", "gemini_context"


MODEL_CAPABILITIES: Dict[str, ModelCapabilities] = {
    # Anthropic models
    "claude-sonnet": ModelCapabilities(
        prompt_cache_strategy="anthropic_system_and_3",
        max_output_tokens=8192,
        context_window=200000,
    ),
    "claude-3-5-sonnet": ModelCapabilities(
        prompt_cache_strategy="anthropic_system_and_3",
        max_output_tokens=8192,
        context_window=200000,
    ),
    "claude-3-7-sonnet": ModelCapabilities(
        prompt_cache_strategy="anthropic_system_and_3",
        max_output_tokens=64000,
        context_window=200000,
    ),
    "claude-opus": ModelCapabilities(
        prompt_cache_strategy="anthropic_system_and_3",
        max_output_tokens=8192,
        context_window=200000,
    ),
    "claude-haiku": ModelCapabilities(
        prompt_cache_strategy="anthropic_system_and_3",
        max_output_tokens=8192,
        context_window=200000,
    ),

    "gemini-3.8-flash": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=65536,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-3.7-flash": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=65536,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-3.6-flash": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=65536,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-3.5-flash": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=65536,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-3.5-flash-lite": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=32768,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-3.1-flash-lite": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=32768,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-2.5-flash": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=65536,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-2.0-flash": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=65536,
        context_window=1048576,
        supports_tool_choice=True,
    ),
    "gemini-1.5-pro": ModelCapabilities(
        prompt_cache_strategy="gemini_context",
        max_output_tokens=65536,
        context_window=2097152,
        supports_tool_choice=True,
    ),

    # DeepSeek models
    "deepseek-reasoner": ModelCapabilities(
        supports_tool_choice=False,
        requires_reasoning_roundtrip=True,
        requires_reasoning_split=True,
        prompt_cache_strategy="deepseek_prefix",
        max_output_tokens=8192,
        context_window=64000,
    ),
    "deepseek-chat": ModelCapabilities(
        supports_tool_choice=True,
        prompt_cache_strategy="deepseek_prefix",
        max_output_tokens=8192,
        context_window=64000,
    ),

    # OpenAI models
    "gpt-4o": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=16384,
        context_window=128000,
    ),
    "gpt-4o-mini": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=16384,
        context_window=128000,
    ),
    "o1": ModelCapabilities(
        supports_tool_choice=False,
        prompt_cache_strategy="none",
        max_output_tokens=32768,
        context_window=128000,
    ),
    "o3-mini": ModelCapabilities(
        supports_tool_choice=False,
        prompt_cache_strategy="none",
        max_output_tokens=65536,
        context_window=200000,
    ),

    # Groq / OpenRouter models
    "groq": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=8192,
        context_window=128000,
    ),
    "llama": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=8192,
        context_window=128000,
    ),
    "qwen": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=16384,
        context_window=131072,
    ),
    "glm": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=8192,
        context_window=128000,
    ),
    "minimax": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=8192,
        context_window=128000,
    ),
    "jev": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=2048,
        context_window=64000,
        supports_tool_choice=False,
        supports_streaming=False,
    ),
    "typesafe": ModelCapabilities(
        prompt_cache_strategy="none",
        max_output_tokens=2048,
        context_window=64000,
        supports_tool_choice=False,
        supports_streaming=False,
    ),
}


def get_capabilities(model_name: str) -> ModelCapabilities:
    """Look up capabilities for a model, with fuzzy lowercase prefix matching."""
    lower = str(model_name or "").lower().strip()
    for prefix, caps in MODEL_CAPABILITIES.items():
        if prefix in lower:
            return caps
    return ModelCapabilities()  # Safe defaults
