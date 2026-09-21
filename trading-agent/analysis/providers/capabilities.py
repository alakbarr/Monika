# ==============================================================================
# File: analysis/providers/capabilities.py
# ==============================================================================

"""
Declarative Model Capabilities Table.
Centralizes LLM feature flags (tool choice, structured output, caching, reasoning)
to eliminate scattered ad-hoc if/else branching across providers.
"""

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
        max_output_tokens=16384,
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
    "gemini-2.5-pro": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        context_window=1048576,
        prompt_cache_strategy="gemini_context",
        supports_native_thinking=True,
    ),
    "gemini-2.5-flash": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=8192,
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
    "gpt-4o": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=4096,
    ),
    "gpt-4o-mini": ModelCapabilities(
        supports_caching=True,
        supports_structured_output=True,
        max_output_tokens=4096,
    ),
    "o1": ModelCapabilities(
        supports_tool_choice=False,
        supports_structured_output=True,
        requires_reasoning_split=True,
        max_output_tokens=16384,
    ),
    "o3-mini": ModelCapabilities(
        supports_tool_choice=True,
        supports_structured_output=True,
        requires_reasoning_split=True,
        max_output_tokens=16384,
    ),

    # DeepSeek
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
    "qwen3.6-27b": ModelCapabilities(
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
}

DEFAULT_CAPABILITIES = ModelCapabilities()


def get_model_capabilities(model_name: Optional[str]) -> ModelCapabilities:
    """
    Look up capabilities for a model with prefix/substring matching and graceful default fallback.
    """
    if not model_name:
        return DEFAULT_CAPABILITIES

    clean_name = model_name.strip().lower()

    # Exact match
    if clean_name in MODEL_CAPABILITIES:
        return MODEL_CAPABILITIES[clean_name]

    # Partial / prefix match
    for key, caps in MODEL_CAPABILITIES.items():
        if key in clean_name or clean_name in key:
            return caps

    # Provider heuristic fallbacks
    if "jev" in clean_name or "typesafe" in clean_name:
        return ModelCapabilities(
            supports_tool_choice=False,
            supports_json_mode=True,
            supports_structured_output=True,
            supports_streaming=False,
            max_output_tokens=2048,
            context_window=64000,
            supports_caching=False,
            supports_native_thinking=False,
        )
    if "claude" in clean_name:
        return ModelCapabilities(supports_caching=True, supports_structured_output=True)
    if "gemini" in clean_name:
        return ModelCapabilities(supports_caching=True, supports_structured_output=True)
    if "gpt-4" in clean_name:
        return ModelCapabilities(supports_caching=True, supports_structured_output=True)
    if "deepseek-reasoner" in clean_name or "r1" in clean_name:
        return ModelCapabilities(supports_tool_choice=False, requires_reasoning_roundtrip=True, prompt_cache_strategy="none")

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

    # Tier 5: Safe lower bound default
    return DEFAULT_CAPABILITIES.context_window if DEFAULT_CAPABILITIES.context_window > 0 else 32768
