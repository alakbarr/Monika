# ==============================================================================
# File: analysis/providers/capabilities.py
# ==============================================================================

"""
Declarative Model Capabilities Table.
Centralizes LLM feature flags (tool choice, structured output, caching, reasoning)
to eliminate scattered ad-hoc if/else branching across providers.
"""

import re
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ModelCapabilities:
    """Declarative capability flags for a model or family of models."""

    supports_tool_choice: bool = True
    supports_json_mode: bool = True
    supports_structured_output: bool = True
    supports_streaming: bool = True
    requires_reasoning_roundtrip: bool = False
    requires_reasoning_split: bool = False
    max_output_tokens: int = 8192
    context_window: int = 200000
    prompt_cache_strategy: str = "none"
    supports_caching: bool = False
    normalize_content: bool = False
    supports_native_thinking: bool = False


# Known model capability registry
MODEL_CAPABILITIES: Dict[str, ModelCapabilities] = {
    # Anthropic
    "claude-opus-5.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "opus-5.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-sonnet-5.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "sonnet-5.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-fable-5.1": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "fable-5.1": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-fable-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-haiku-5.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=False,
    ),
    "haiku-5.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=False,
    ),
    "claude-sonnet-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=500000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-5-sonnet": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=500000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-opus-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=500000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-3-5-sonnet": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-3-7-sonnet": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-3-5-haiku": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
    ),
    "claude-3-haiku": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=4096,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
    ),
    # Google Gemini
    "gemini-4-argon": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=1000000,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.8-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.7-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=1048576,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.6-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.5-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.5-flash-lite": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=1048576,
        prompt_cache_strategy="gemini_context",
    ),
    "gemini-3.1-flash-lite": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=1048576,
        prompt_cache_strategy="gemini_context",
    ),
    "gemini-3.1-pro-preview": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.1-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.8-live": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=1048576,
    ),
    "gemini-3.8-live-extended-thinking": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=1048576,
        supports_native_thinking=True,
    ),
    "gemini-3.5-transcribe-live": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=False,
        max_output_tokens=4096,
        context_window=1048576,
    ),
    "gemini-3-flash-live": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=1048576,
    ),
    "gemini-3.8-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-2.5-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=1048576,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-2.5-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=1048576,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-2.0-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
    ),
    "gemini-1.5-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
    ),
    "gemini-1.5-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
    ),
    # OpenAI
    "gpt-6": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=500000,
        supports_native_thinking=True,
    ),
    "gpt-6-astra": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=500000,
        supports_native_thinking=True,
    ),
    "gpt-6.1-sol": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=1050000,
        supports_native_thinking=True,
    ),
    "gpt-6-sol": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=500000,
        supports_native_thinking=True,
    ),
    "gpt-6-luna": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=500000,
        supports_native_thinking=True,
    ),
    "o3": ModelCapabilities(
        supports_tool_choice=True,
        supports_structured_output=True,
        requires_reasoning_split=True,
        max_output_tokens=32768,
        context_window=200000,
    ),
    "o4": ModelCapabilities(
        supports_tool_choice=True,
        supports_structured_output=True,
        requires_reasoning_split=True,
        max_output_tokens=32768,
        context_window=500000,
    ),
    "gpt-4o": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
    ),
    "gpt-4o-mini": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
    ),
    "o1": ModelCapabilities(
        supports_tool_choice=False,
        supports_structured_output=True,
        requires_reasoning_split=True,
        max_output_tokens=65536,
    ),
    "o3-mini": ModelCapabilities(
        supports_tool_choice=True,
        supports_structured_output=True,
        requires_reasoning_split=True,
        max_output_tokens=65536,
        supports_native_thinking=True,
    ),
    # DeepSeek
    "deepseek-v4-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=256000,
        supports_native_thinking=True,
    ),
    "deepseek-v4.1-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=256000,
        supports_native_thinking=True,
    ),
    "deepseek-v4-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=256000,
        supports_native_thinking=True,
    ),
    "deepseek-v4": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=256000,
        supports_native_thinking=True,
    ),
    "deepseek-chat": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=8192,
    ),
    "deepseek-reasoner": ModelCapabilities(
        supports_tool_choice=False,
        requires_reasoning_roundtrip=True,
        max_output_tokens=8192,
        supports_native_thinking=True,
    ),
    # Groq / OpenRouter
    "groq-compound": ModelCapabilities(
        max_output_tokens=8192,
        supports_caching=False,
    ),
    "groq/compound": ModelCapabilities(
        max_output_tokens=8192,
        supports_caching=False,
    ),
    "groq-compound-mini": ModelCapabilities(
        max_output_tokens=8192,
        supports_caching=False,
    ),
    "groq/compound-mini": ModelCapabilities(
        max_output_tokens=8192,
        supports_caching=False,
    ),
    "llama-3.3-70b": ModelCapabilities(
        max_output_tokens=32768,
        supports_structured_output=True,
    ),
    "llama-3.1-8b": ModelCapabilities(
        max_output_tokens=8192,
        supports_structured_output=True,
    ),
    "qwen3.8-27b": ModelCapabilities(
        max_output_tokens=32768,
        supports_structured_output=True,
    ),
    "groq-qwen3.8-27b": ModelCapabilities(
        max_output_tokens=32768,
        supports_structured_output=True,
    ),
    "qwen/qwen3.8-27b": ModelCapabilities(
        max_output_tokens=32768,
        supports_structured_output=True,
    ),
    "qwen3.6-27b": ModelCapabilities(
        max_output_tokens=32768,
        supports_structured_output=True,
    ),
    "groq-qwen3.6-27b": ModelCapabilities(
        max_output_tokens=32768,
        supports_structured_output=True,
    ),
    "groq-gpt-oss-120b": ModelCapabilities(
        max_output_tokens=65536,
        supports_structured_output=True,
    ),
    "groq-gpt-oss-20b": ModelCapabilities(
        max_output_tokens=65536,
        supports_structured_output=True,
    ),
    # Zhipu / GLM Frontier
    "glm-5.3": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "glm-5.3-flash": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    # Meta Frontier
    "muse-spark-1.3": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "muse-spark-1.3-contributor": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "muse-spark-1.2": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "muse-spark-1.2-contributor": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "muse-wonder": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "wonder-full": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=256000,
        supports_native_thinking=True,
    ),
    # xAI Frontier
    "grok-4.7": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=256000,
        supports_native_thinking=True,
    ),
    "grok-4.7-vision": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=256000,
        supports_native_thinking=True,
    ),
    # Moonshot AI Frontier
    "kimi-k3": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=256000,
        supports_native_thinking=True,
    ),
    # TypeSafe Jev System One
    "jev-latest": ModelCapabilities(
        supports_tool_choice=False,
        supports_json_mode=True,
        supports_structured_output=True,
        supports_streaming=False,
        max_output_tokens=2048,
        context_window=64000,
        supports_caching=False,
        supports_native_thinking=False,
    ),
    "jev-1.13": ModelCapabilities(
        supports_tool_choice=False,
        supports_json_mode=True,
        supports_structured_output=True,
        supports_streaming=False,
        max_output_tokens=2048,
        context_window=64000,
        supports_caching=False,
        supports_native_thinking=False,
    ),
    # 9Router Key & Free Models
    "kr/claude-sonnet-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "kr/claude-opus-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "oc/union-alpha": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    "if/kimi-k2": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    "if/deepseek-v3.2": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    "mmf/mimo-auto": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=4096,
        context_window=32768,
    ),
    "combo/free-fallback": ModelCapabilities(
        supports_caching=False,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    # --- Full Catalog Canonical Registrations ---
    # Anthropic / Claude
    "claude-sonnet-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "sonnet-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-sonnet-4.6": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "sonnet-4.6": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-sonnet-4-6": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-opus-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "opus-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-opus-4.6": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "opus-4.6": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-opus-4.7": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "opus-4.7": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-opus-4.8": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "opus-4.8": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "opus-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=500000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "sonnet-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=64000,
        context_window=500000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    "claude-haiku-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=False,
    ),
    "haiku-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=False,
    ),
    "claude-haiku-4-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=False,
    ),
    "fable-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=200000,
        prompt_cache_strategy="anthropic_system_and_3",
        supports_native_thinking=True,
    ),
    # Google / Gemini
    "gemini-3.0-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=1048576,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-3.8-flash-high": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=2097152,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    # OpenAI / GPT Frontier & Reasoning
    "gpt-5.4": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "gpt-5.4-mini": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "gpt-5.4-nano": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "gpt-5.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "gpt-5.6-luna": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-5.6-luna-max": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-5.6-luna-xhigh": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-5.6-sol": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-5.6-sol-high": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-5.6-sol-medium": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-5.6-terra": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-6-luna": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-6-luna-decision": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-6-luna-max": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "gpt-6-luna-xhigh": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=200000,
        supports_native_thinking=True,
    ),
    "luna-decision": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "gpt-oss-120b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=65536,
        context_window=128000,
        supports_native_thinking=True,
    ),
    # DeepSeek
    "deepseek-r1": ModelCapabilities(
        supports_tool_choice=False,
        supports_json_mode=True,
        supports_structured_output=True,
        requires_reasoning_roundtrip=True,
        max_output_tokens=65536,
        context_window=128000,
        prompt_cache_strategy="none",
        supports_native_thinking=True,
    ),
    "deepseek-v3.2": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "deepseek-3.2": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    # Qwen
    "qwen3-coder-next": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "qwen3-coder-plus": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "qwen3.8-max": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "qwen3.8-2.4t-a95b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "smart-code": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    # Zhipu / GLM
    "glm-4.7": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "glm-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "glm-5.1": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "glm-5.2": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    # xAI / Grok
    "grok-4.3": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "grok-4.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "grok-4.6": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    # Moonshot / Kimi
    "kimi-k2": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "kimi-k2.7-code": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    # MiniMax
    "minimax-m2.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
    ),
    "minimax-m3": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
    ),
    "minimax-m3.1-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
    ),
    # Nvidia Nemotron
    "nemotron-3-nano": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "nemotron-3-nano-30b-a3b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "nemotron-3-nano-omni": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "nemotron-3-nano-omni-30b-a3b-reasoning": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "nemotron-3-super": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "nemotron-3-super-120b-a12b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "nemotron-3-ultra": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "nemotron-3-ultra-550b-a55b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
        supports_native_thinking=True,
    ),
    "nemotron-3.5-content-safety": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "nemotron-3.5-safety": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "nemotron-3.5-lightning": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "nemotron-nano-12b-vl": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    "nemotron-nano-12b-v2-vl": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    "nemotron-nano-9b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    "nemotron-nano-9b-v2": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    # Gemma
    "gemma-4-26b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "gemma-4-26b-a4b-it": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "gemma-4-31b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "gemma-4-31b-it": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    # Mimo
    "mimo-auto": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=128000,
    ),
    "mimo-v2.5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
    ),
    "mimo-v2.5-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
    ),
    "mimo-v2.6-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
    ),
    "mimo-v2.6-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=32768,
        context_window=128000,
    ),
    # Specialized Models
    "dots-3-note": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=64000,
    ),
    "inkling": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "inkling-small": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "laguna-s-2.1": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "laguna-xs-2.1": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "lfm-2.5-2.6b": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "liquid-d1": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "ling-3.0-flash-fin": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "llama3.2": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
    "mercury-decide": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=64000,
    ),
    "north-mini-code": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "ox-alpha": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "union-alpha": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "step-5": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=16384,
        context_window=64000,
    ),
    "kev-4b": ModelCapabilities(
        supports_tool_choice=False,
        supports_json_mode=True,
        supports_structured_output=True,
        supports_streaming=False,
        max_output_tokens=8192,
        context_window=64000,
        supports_caching=False,
        supports_native_thinking=False,
    ),
    "whisper-large-v3": ModelCapabilities(
        supports_tool_choice=False,
        supports_streaming=False,
        supports_json_mode=False,
        supports_structured_output=False,
        max_output_tokens=448,
        context_window=16000,
    ),
    "whisper-large-v3-turbo": ModelCapabilities(
        supports_tool_choice=False,
        supports_streaming=False,
        supports_json_mode=False,
        supports_structured_output=False,
        max_output_tokens=448,
        context_window=16000,
    ),
    "free": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=128000,
    ),
}

DEFAULT_CAPABILITIES = ModelCapabilities()


def get_model_capabilities(model_name: Optional[str]) -> ModelCapabilities:
    """
    Look up capabilities for a model with prefix/substring matching and graceful default fallback.
    Supports comprehensive canonicalization across all routing prefixes, vendor slugs, and feature suffixes.
    """
    if not model_name:
        return DEFAULT_CAPABILITIES

    clean_name = model_name.strip().lower()

    # Repeatedly strip known router and vendor prefixes
    router_prefixes = (
        "9router/",
        "9r/",
        "kr/",
        "if/",
        "oc/",
        "ocz/",
        "mmf/",
        "gc/",
        "af/",
        "ag/",
        "cx/",
        "cc/",
        "gh/",
        "combo/",
    )
    vendor_prefixes = (
        "anthropic/",
        "google/",
        "openai/",
        "deepseek/",
        "z-ai/",
        "zhipu/",
        "meta/",
        "moonshotai/",
        "moonshot/",
        "minimax/",
        "nvidia/",
        "cohere/",
        "poolside/",
        "thinkingmachines/",
        "liquid/",
        "openrouter/",
        "typesafe/",
        "jaredpalmer/",
        "dots-studio/",
    )
    suffixes = (":free", "-free", "-preview", "-thinking", "-contributor", "-opencode", "-openrouter")

    changed = True
    while changed:
        changed = False
        for p in router_prefixes:
            if clean_name.startswith(p):
                clean_name = clean_name[len(p) :]
                changed = True
                break
        for v in vendor_prefixes:
            if clean_name.startswith(v):
                clean_name = clean_name[len(v) :]
                changed = True
                break

    changed = True
    while changed:
        changed = False
        for s in suffixes:
            if clean_name.endswith(s):
                clean_name = clean_name[: -len(s)]
                changed = True
                break

    clean_name = re.sub(r"-\d{4,8}$", "", clean_name)

    # 1. Exact match in canonical registry
    if clean_name in MODEL_CAPABILITIES:
        return MODEL_CAPABILITIES[clean_name]

    # 2. Substring / longest matching key lookup
    matching_keys = [k for k in MODEL_CAPABILITIES if k in clean_name]
    if matching_keys:
        best_key = max(matching_keys, key=len)
        return MODEL_CAPABILITIES[best_key]

    # 3. Comprehensive family heuristics fallbacks
    if "whisper" in clean_name:
        return ModelCapabilities(
            supports_tool_choice=False,
            supports_streaming=False,
            supports_json_mode=False,
            supports_structured_output=False,
            max_output_tokens=448,
            context_window=16000,
        )
    if "haiku" in clean_name:
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=8192,
            context_window=200000,
            prompt_cache_strategy="anthropic_system_and_3",
            supports_native_thinking=False,
        )
    if any(k in clean_name for k in ("claude", "sonnet", "opus")):
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=64000,
            context_window=200000,
            prompt_cache_strategy="anthropic_system_and_3",
            supports_native_thinking=True,
        )
    if any(k in clean_name for k in ("gemini", "argon")):
        if "transcribe" in clean_name:
            toks = 4096
        elif "live" in clean_name and "extended" not in clean_name:
            toks = 8192
        else:
            toks = 65536
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=toks,
            context_window=1048576,
            prompt_cache_strategy="gemini_context",
            supports_native_thinking=True,
        )
    if any(k in clean_name for k in ("gpt-5.6", "gpt-6", "luna", "sol", "astra", "terra", "gpt-oss")):
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=65536,
            context_window=200000,
            supports_native_thinking=True,
        )
    if any(k in clean_name for k in ("gpt-5.4", "gpt-5.5", "gpt-5")):
        toks = 16384 if "nano" in clean_name else 32768
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=toks,
            context_window=128000,
            supports_native_thinking=True,
        )
    if "deepseek-r1" in clean_name or "r1" in clean_name:
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            supports_tool_choice=False,
            requires_reasoning_roundtrip=True,
            max_output_tokens=65536,
            context_window=128000,
            supports_native_thinking=True,
        )
    if "deepseek-v4" in clean_name or "deepseek-4" in clean_name:
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=32768,
            context_window=128000,
            supports_native_thinking=True,
        )
    if "deepseek" in clean_name:
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=16384,
            context_window=128000,
        )
    if any(k in clean_name for k in ("qwen3", "smart-code")):
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=32768,
            context_window=128000,
            supports_native_thinking=True,
        )
    if any(k in clean_name for k in ("glm-5", "grok", "kimi", "minimax")):
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=32768,
            context_window=128000,
            supports_native_thinking=True,
        )
    if any(k in clean_name for k in ("nemotron-3-ultra", "nemotron-3-super", "reasoning")):
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=32768,
            context_window=128000,
            supports_native_thinking=True,
        )
    if any(
        k in clean_name
        for k in (
            "nemotron",
            "gemma",
            "mimo",
            "laguna",
            "inkling",
            "lfm",
            "liquid",
            "muse",
            "north",
            "step-5",
            "ling",
            "union",
            "ox-alpha",
        )
    ):
        return ModelCapabilities(
            supports_caching=True,
            supports_structured_output=True,
            max_output_tokens=16384,
            context_window=64000,
        )
    if any(k in clean_name for k in ("jev", "kev", "typesafe")):
        return ModelCapabilities(
            supports_tool_choice=False,
            supports_json_mode=True,
            supports_structured_output=True,
            supports_streaming=False,
            max_output_tokens=8192,
            context_window=64000,
            supports_caching=False,
            supports_native_thinking=False,
        )

    return DEFAULT_CAPABILITIES


get_capabilities = get_model_capabilities


def resolve_effective_context_window(
    model_name: Optional[str],
    provider_name: Optional[str] = None,
    settings: Optional[dict] = None,
    proxy_limit: Optional[int] = None,
) -> int:
    """
    Multi-Tier Context Window Resolution Cascade:
    1. Explicit proxy_limit parameter (if passed by proxy / gateway / router).
    2. settings.yaml override (llm.models.<model>.context_window or llm.providers.<provider>.context_window).
    3. ModelCapabilities table (MODEL_CAPABILITIES[model_name].context_window).
    4. Provider default heuristic (gemini: 1M, anthropic: 200k, deepseek/openai: 128k, groq: 32k).
    5. Safe fallback lower bound (32768).
    """
    # Tier 1: Explicit proxy limit
    if proxy_limit is not None and proxy_limit > 0:
        return int(proxy_limit)

    clean_model = (model_name or "").strip().lower()
    clean_prov = (provider_name or "").strip().lower()

    # Tier 2: Settings override
    if isinstance(settings, dict):
        llm_cfg = settings.get("llm", {})
        if isinstance(llm_cfg, dict):
            # Model-specific config
            models_cfg = llm_cfg.get("models", {})
            if isinstance(models_cfg, dict) and clean_model in models_cfg:
                m_entry = models_cfg[clean_model]
                if isinstance(m_entry, dict) and "context_window" in m_entry:
                    return int(m_entry["context_window"])
            # Provider-specific config
            provs_cfg = llm_cfg.get("providers", {})
            if isinstance(provs_cfg, dict) and clean_prov in provs_cfg:
                p_entry = provs_cfg[clean_prov]
                if isinstance(p_entry, dict) and "context_window" in p_entry:
                    return int(p_entry["context_window"])
        # Global fallback in settings
        if "context_window" in settings and isinstance(settings["context_window"], int):
            return int(settings["context_window"])

    # Tier 3: ModelCapabilities table lookup
    if clean_model:
        caps = get_model_capabilities(clean_model)
        if caps and caps.context_window and caps.context_window != DEFAULT_CAPABILITIES.context_window:
            return caps.context_window

    # Tier 4: Provider heuristics
    if "gemini" in clean_model or clean_prov == "gemini":
        return 1048576
    if "claude" in clean_model or clean_prov == "anthropic":
        return 200000
    if "deepseek" in clean_model or clean_prov == "deepseek":
        return 128000
    if "gpt" in clean_model or "o1" in clean_model or "o3" in clean_model or clean_prov == "openai":
        return 128000
    if "groq" in clean_model or clean_prov == "groq":
        return 32768
    if "jev" in clean_model or clean_prov == "typesafe":
        return 64000
    if clean_prov == "ollama":
        return 32768
    if clean_prov in ("9router", "ninerouter", "nine_router"):
        return 128000

    # Tier 5: Safe lower bound default
    return DEFAULT_CAPABILITIES.context_window if DEFAULT_CAPABILITIES.context_window > 0 else 32768


def resolve_stale_timeout_floor(
    model_name: Optional[str],
    default_timeout: float = 30.0,
) -> float:
    """
    Enforces minimum timeout floors for reasoning models to prevent premature disconnects.
    Frontier reasoning engines (o1, o3, R1, Sonnet 3.7 Thinking, Gemini Pro Thinking)
    require 180s - 600s timeout floors.
    """
    if not model_name:
        return default_timeout

    clean = model_name.strip().lower()

    # Extreme reasoning models (up to 10 min)
    if any(k in clean for k in ("o1-pro", "o3", "deepseek-reasoner", "r1-full", "opus-5-thinking")):
        return max(default_timeout, 300.0)

    # Standard reasoning models (up to 3 min)
    if any(k in clean for k in ("o1", "r1", "thinking", "reasoning", "sonnet-3-7", "sonnet-5")):
        return max(default_timeout, 180.0)

    return default_timeout


def clamp_reasoning_effort(
    model_name: str,
    requested_effort: str,
) -> str:
    """
    Maps requested reasoning effort ('high', 'medium', 'low') to the closest supported
    effort level for the specified model family without raising schema errors.
    """
    effort = (requested_effort or "medium").strip().lower()
    valid_levels = ("low", "medium", "high")

    if effort not in valid_levels:
        effort = "medium"

    clean = model_name.strip().lower()

    # Models supporting only low / medium or fixed
    if "o3-mini" in clean:
        return effort  # supports low, medium, high
    if "o1-mini" in clean:
        return "medium"  # o1-mini doesn't support custom effort levels

    return effort


def resolve_effective_max_tokens(
    model_name: Optional[str],
    provider_name: Optional[str] = None,
    requested_max_tokens: Optional[int] = None,
    thinking_budget: Optional[int] = None,
    thinking_level: Optional[str] = None,
    settings: Optional[dict] = None,
    min_answer_headroom: int = 4096,
) -> int:
    """
    Multi-Tier Max Output Tokens Resolution Cascade:
    1. Explicit settings override (llm.models.<model>.max_tokens or llm.providers.<prov>.max_tokens).
    2. Provider strict hardware/API ceilings (Groq, DeepSeek Direct).
    3. ModelCapabilities table lookup with prefix/suffix normalization.
    4. Thinking-aware auto-expansion: if thinking is active, ensures
       effective_max_tokens >= thinking_budget + min_answer_headroom (capped at model ceiling).
    5. Respect caller requested_max_tokens when larger, clamped to hard ceiling.
    6. Safe lower bound default.
    """
    clean_model = (model_name or "").strip().lower()
    clean_prov = (provider_name or "").strip().lower()

    # Tier 1: Settings override
    if isinstance(settings, dict):
        llm_cfg = settings.get("llm", {})
        if isinstance(llm_cfg, dict):
            models_cfg = llm_cfg.get("models", {})
            if isinstance(models_cfg, dict) and clean_model in models_cfg:
                m_entry = models_cfg[clean_model]
                if isinstance(m_entry, dict) and "max_tokens" in m_entry:
                    return int(m_entry["max_tokens"])
            provs_cfg = llm_cfg.get("providers", {})
            if isinstance(provs_cfg, dict) and clean_prov in provs_cfg:
                p_entry = provs_cfg[clean_prov]
                if isinstance(p_entry, dict) and "max_tokens" in p_entry:
                    return int(p_entry["max_tokens"])

    # Tier 2 & 3: ModelCapabilities lookup
    caps = get_model_capabilities(clean_model)
    model_ceiling = caps.max_output_tokens if caps and caps.max_output_tokens else 8192

    # Provider strict hardware / API policy ceilings
    if "groq" in clean_prov or "groq" in clean_model:
        if "oss" in clean_model:
            model_ceiling = min(model_ceiling, 65536)
        elif "qwen" in clean_model or "70b" in clean_model:
            model_ceiling = min(model_ceiling, 32768)
        else:
            model_ceiling = min(model_ceiling, 8192)
    elif clean_prov == "deepseek" and "openrouter" not in clean_prov:
        # Official direct DeepSeek API enforces 8,192 max completion
        model_ceiling = min(model_ceiling, 8192)
    elif ("openrouter" in clean_prov or "openrouter" in clean_model) and "deepseek" in clean_model:
        # OpenRouter third-party host ceiling
        model_ceiling = max(model_ceiling, 32768)
    elif "claude-3-7" in clean_model or "claude-3.7" in clean_model:
        model_ceiling = max(model_ceiling, 64000)
    elif any(k in clean_model for k in ("gemini-2.0", "gemini-2.5", "gemini-3")):
        model_ceiling = max(model_ceiling, 65536)
    elif any(k in clean_model for k in ("o1", "o3")):
        model_ceiling = max(model_ceiling, 65536)

    # Tier 4: Thinking Budget Resolution
    lvl = (thinking_level or "none").strip().lower()
    level_to_budget = {
        "none": 0,
        "off": 0,
        "minimal": 1024,
        "low": 2048,
        "medium": 4096,
        "high": 8192,
        "xhigh": 16384,
        "extended": 16384,
        "max": 16000,
    }
    resolved_budget = (
        thinking_budget if (thinking_budget is not None and thinking_budget > 0) else level_to_budget.get(lvl, 0)
    )

    # Tier 5: Compute Effective Max Tokens
    if resolved_budget > 0:
        # When thinking is active, ensure room for BOTH thinking and visible answer
        needed = resolved_budget + min_answer_headroom
        if requested_max_tokens is not None and requested_max_tokens > 0:
            needed = max(needed, requested_max_tokens + resolved_budget)
        effective = min(needed, model_ceiling)
        effective = max(effective, min(min_answer_headroom, model_ceiling))
    else:
        # Non-thinking mode
        if requested_max_tokens is not None and requested_max_tokens > 0:
            effective = min(requested_max_tokens, model_ceiling)
        else:
            effective = min(8192, model_ceiling)

    return effective
