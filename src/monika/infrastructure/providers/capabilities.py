# ==============================================================================
# File: infrastructure/providers/capabilities.py
# ==============================================================================

"""
Declarative Model Capabilities Resolver.
Centralizes LLM feature flags (tool choice, structured output, caching, reasoning)
to eliminate scattered ad-hoc if/else branching across providers.
"""

import re
from typing import Optional

from monika.infrastructure.providers.capabilities_catalog import (
    DEFAULT_CAPABILITIES,
    MODEL_CAPABILITIES,
    ModelCapabilities,
)

__all__ = [
    "DEFAULT_CAPABILITIES",
    "MODEL_CAPABILITIES",
    "ModelCapabilities",
    "clamp_reasoning_effort",
    "get_model_capabilities",
    "resolve_effective_context_window",
    "resolve_effective_max_tokens",
    "resolve_stale_timeout_floor",
]


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

    clean_model = str(model_name).strip().lower() if isinstance(model_name, str) else ""
    clean_prov = str(provider_name).strip().lower() if isinstance(provider_name, str) else ""

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
    model_name: Optional[str] = None,
    default_timeout: float = 30.0,
    thinking_level: Optional[str] = None,
    thinking_budget: Optional[int] = None,
    supports_native_thinking: Optional[bool] = None,
) -> float:
    """
    Enforces minimum timeout floors for reasoning models to prevent premature disconnects.
    Evaluates thinking_level, thinking_budget, and native thinking capabilities dynamically,
    making timeout allocation future-proof and model-agnostic across any provider.
    """
    # 1. Dynamic capability: explicit thinking level or thinking budget
    if thinking_level and str(thinking_level).lower() not in ("none", "off", ""):
        lvl = str(thinking_level).lower()
        if lvl in ("high", "max", "extended", "xhigh"):
            return max(default_timeout, 600.0)
        return max(default_timeout, 360.0)

    if thinking_budget is not None and thinking_budget > 0:
        if thinking_budget >= 8192:
            return max(default_timeout, 600.0)
        return max(default_timeout, 360.0)

    if supports_native_thinking:
        return max(default_timeout, 360.0)

    if not model_name:
        return default_timeout

    clean = model_name.strip().lower()

    # Generic reasoning/thinking suffixes or tags used across providers
    if any(k in clean for k in ("reasoning", "reasoner", "thinking", "thought")):
        return max(default_timeout, 360.0)

    # Common frontier reasoning architectures
    if any(k in clean for k in ("o1", "o3", "o4", "r1", "argon")):
        return max(default_timeout, 360.0)

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
    clean_model = str(model_name).strip().lower() if isinstance(model_name, str) else ""
    clean_prov = str(provider_name).strip().lower() if isinstance(provider_name, str) else ""

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
    if isinstance(thinking_level, str):
        lvl = thinking_level.strip().lower()
    else:
        lvl = "none"
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
        int(thinking_budget)
        if isinstance(thinking_budget, (int, float)) and not isinstance(thinking_budget, bool) and thinking_budget > 0
        else level_to_budget.get(lvl, 0)
    )

    # Tier 5: Compute Effective Max Tokens
    if resolved_budget > 0:
        # When thinking is active, ensure room for BOTH thinking and visible answer
        needed = resolved_budget + min_answer_headroom
        if (
            isinstance(requested_max_tokens, (int, float))
            and not isinstance(requested_max_tokens, bool)
            and requested_max_tokens > 0
        ):
            needed = max(needed, requested_max_tokens + resolved_budget)
        effective = min(needed, model_ceiling)
        effective = max(effective, min(min_answer_headroom, model_ceiling))
    else:
        # Non-thinking mode
        if (
            isinstance(requested_max_tokens, (int, float))
            and not isinstance(requested_max_tokens, bool)
            and requested_max_tokens > 0
        ):
            effective = min(requested_max_tokens, model_ceiling)
        else:
            effective = min(8192, model_ceiling)

    return effective
