# ==============================================================================
# File: utils/llm/context_tracker.py
# Description: Lightweight Centralized Context Window & Token Accumulator (Q5)
# ==============================================================================

"""
Context window tracking and token accumulator for Monika AI Trading Agent.

Addresses Open Question 5:
- Centralized tracking of tokens used so far per conversation and analysis cycle.
- Integrates with ModelCapabilities to know exact model context limits (e.g. 200k, 1M).
- Provides context utilization ratio, cache hit metrics, and budget alerts for TUI and API.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.llm.model_capabilities import MODEL_CAPABILITIES, get_capabilities

logger = logging.getLogger("TradingAgent.Utils.ContextTracker")


@dataclass
class TokenSpan:
    """Record of a single token consumption event."""
    step: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    model: str


class ContextTracker:
    """
    Accumulates token usage across pipeline steps, subagents, and chat sessions.
    Tracks active cycle usage relative to current model context window limits.
    """

    def __init__(self, default_model: str = "claude-3-5-sonnet"):
        self.default_model = default_model
        self.current_model = default_model
        self.current_cycle_id: Optional[str] = None
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cached_tokens: int = 0
        self.spans: List[TokenSpan] = []

    @property
    def max_context_window(self) -> int:
        """Retrieve model context window limit from declared capabilities."""
        caps = get_capabilities(self.current_model)
        return caps.context_window if caps else 200000

    def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        model: Optional[str] = None,
        step: str = "general",
    ) -> None:
        """Record token usage from a model invocation."""
        inp = max(0, int(input_tokens or 0))
        out = max(0, int(output_tokens or 0))
        cache = max(0, int(cached_tokens or 0))

        if model:
            self.current_model = model

        self.input_tokens += inp
        self.output_tokens += out
        self.cached_tokens += cache

        self.spans.append(
            TokenSpan(
                step=step,
                input_tokens=inp,
                output_tokens=out,
                cached_tokens=cache,
                model=self.current_model,
            )
        )

    def get_used_tokens(self) -> int:
        """Current total tokens accumulated in the active cycle."""
        return self.input_tokens + self.output_tokens

    def get_utilization_ratio(self) -> float:
        """Ratio of context window used (0.0 - 1.0)."""
        max_limit = self.max_context_window
        if max_limit <= 0:
            return 0.0
        return min(1.0, max(0.0, self.get_used_tokens() / float(max_limit)))

    def get_cache_hit_rate(self) -> float:
        """Percentage of input tokens served from cache."""
        total_in = self.input_tokens + self.cached_tokens
        if total_in <= 0:
            return 0.0
        return (self.cached_tokens / float(total_in)) * 100.0

    def is_approaching_limit(self, threshold: float = 0.8) -> bool:
        """Returns True if used tokens exceed the given threshold ratio."""
        return self.get_utilization_ratio() >= threshold

    def reset(self, cycle_id: Optional[str] = None, model: Optional[str] = None) -> None:
        """Reset accumulator for a new cycle or conversation."""
        self.current_cycle_id = cycle_id
        if model:
            self.current_model = model
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.spans.clear()

    def get_summary(self) -> Dict[str, Any]:
        """Comprehensive snapshot dictionary for dashboard status bars and metrics."""
        return {
            "cycle_id": self.current_cycle_id,
            "model": self.current_model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "used_tokens": self.get_used_tokens(),
            "max_context_window": self.max_context_window,
            "utilization_ratio": round(self.get_utilization_ratio(), 4),
            "utilization_pct": round(self.get_utilization_ratio() * 100.0, 1),
            "cache_hit_rate": round(self.get_cache_hit_rate(), 1),
            "span_count": len(self.spans),
        }


# Global singleton instance for easy cross-module access
_global_context_tracker = ContextTracker()


def get_context_tracker() -> ContextTracker:
    """Retrieve global ContextTracker instance."""
    return _global_context_tracker
