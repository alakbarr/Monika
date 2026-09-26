# ==============================================================================
# File: analysis/memory/prompt_cache_boundary.py
# ==============================================================================

"""
Prompt Cache Boundary & Stable Prefix Registry.
Provides deterministic request partitioning to maximize KV-cache hit ratios
(Anthropic prompt caching, OpenAI prefix caching, OpenRouter cache routing).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger("TradingAgent.Analysis.Memory.PromptCacheBoundary")

_LOCK = threading.Lock()
_STABLE_PREFIX_REGISTRY: List[str] = []
MAX_PREFIX_ENTRIES = 64
MIN_PREFIX_CHARS = 200  # Only cache blocks large enough to yield cost/latency savings


@dataclass
class PromptCacheProfile:
    min_cacheable_tokens: int = 50
    max_breakpoints: int = 4
    cache_control_type: str = "ephemeral"


@dataclass
class CacheBoundaryPlan:
    messages: List[Dict[str, Any]] = field(default_factory=list)
    breakpoint_indices: List[int] = field(default_factory=list)
    estimated_cached_tokens: int = 0


class PromptCacheBoundaryPlanner:
    """Class interface for deterministic prompt cache boundary planning."""

    def __init__(self, profile: Optional[PromptCacheProfile] = None):
        self.profile = profile or PromptCacheProfile()
        self._custom_prefixes: Dict[str, str] = {}

    def register_stable_prefix(self, name: str, prefix_text: str) -> None:
        self._custom_prefixes[name] = prefix_text
        register_stable_prefix(prefix_text)

    def plan_boundaries(
        self,
        messages: List[Dict[str, Any]],
        provider: str = "anthropic",
    ) -> CacheBoundaryPlan:
        formatted = plan_prompt_cache_boundaries(messages, provider=provider)
        breakpoints = []
        for idx, m in enumerate(formatted):
            content = m.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "cache_control" in part:
                        breakpoints.append(idx)
                        break
            elif isinstance(m.get("cache_control"), dict):
                breakpoints.append(idx)

        return CacheBoundaryPlan(
            messages=formatted,
            breakpoint_indices=breakpoints,
            estimated_cached_tokens=len(breakpoints) * self.profile.min_cacheable_tokens,
        )


def register_stable_prefix(prefix_text: str) -> None:
    """Registers a reusable static text block (e.g. trading soul, invariant rules)."""
    if not prefix_text or len(prefix_text.strip()) < MIN_PREFIX_CHARS:
        return

    cleaned = prefix_text.strip()
    with _LOCK:
        if cleaned not in _STABLE_PREFIX_REGISTRY:
            _STABLE_PREFIX_REGISTRY.append(cleaned)
            if len(_STABLE_PREFIX_REGISTRY) > MAX_PREFIX_ENTRIES:
                _STABLE_PREFIX_REGISTRY.pop(0)
            logger.debug(f"[PromptCacheBoundary] Registered stable prefix ({len(cleaned)} chars)")


def find_stable_prefix(content: str) -> Optional[str]:
    """Finds the longest registered prefix that matches the beginning of content."""
    if not content:
        return None

    stripped = content.strip()
    with _LOCK:
        best_match = None
        for prefix in _STABLE_PREFIX_REGISTRY:
            if stripped.startswith(prefix):
                if best_match is None or len(prefix) > len(best_match):
                    best_match = prefix
        return best_match


def plan_prompt_cache_boundaries(
    messages: List[Dict[str, Any]],
    provider: str = "anthropic",
) -> List[Dict[str, Any]]:
    """
    Scans a message list and injects ephemeral cache markers at appropriate boundaries.
    For Anthropic, attaches `cache_control: {"type": "ephemeral"}` to system prompt
    and last stable conversation checkpoints.
    """
    if not messages:
        return []

    provider_lower = provider.lower()
    supports_ephemeral = "anthropic" in provider_lower or "openrouter" in provider_lower

    if not supports_ephemeral:
        return messages

    formatted: List[Dict[str, Any]] = []

    # 1. System prompt caching
    for idx, msg in enumerate(messages):
        msg_copy = dict(msg)
        content = msg_copy.get("content")

        # Check for system message or first large message
        if msg_copy.get("role") == "system" or idx == 0:
            if isinstance(content, str) and len(content) >= MIN_PREFIX_CHARS:
                # Convert string content to multipart block with cache_control
                msg_copy["content"] = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
                formatted.append(msg_copy)
                continue

        formatted.append(msg_copy)

    # 2. Mark checkpoint near the end of durable history (2 turns before tail)
    if len(formatted) >= 4:
        target_idx = len(formatted) - 3
        target_msg = formatted[target_idx]
        t_content = target_msg.get("content")
        if isinstance(t_content, str):
            target_msg["content"] = [
                {
                    "type": "text",
                    "text": t_content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        elif isinstance(t_content, list) and t_content:
            last_part = dict(t_content[-1])
            last_part["cache_control"] = {"type": "ephemeral"}
            t_content[-1] = last_part

    return formatted
