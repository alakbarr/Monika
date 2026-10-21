"""
Cache Miss Detector — identifies prompt cache misses and calculates financial waste.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.CacheMissDetector")

CACHE_TTL_MS = 5 * 60 * 1000  # 5 minutes (Anthropic / Gemini ephemeral cache TTL)


class CacheMissReason(str):
    """Case-insensitive and alias-aware string for cache miss root-cause classification."""

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, str):
            return False
        s_self = str(self).upper()
        s_other = other.upper()
        if s_self == s_other:
            return True
        aliases = {
            "TTL_EXPIRED": {"TTL_EXPIRED"},
            "PREFIX_MUTATED": {"PREFIX_MUTATED", "PREFIX_CHANGED"},
            "MODEL_OR_KEY_CHANGED": {"MODEL_OR_KEY_CHANGED", "MODEL_CHANGED"},
            "FIRST_CALL": {"FIRST_CALL"},
            "NONE": {"NONE"},
        }
        for canon, syns in aliases.items():
            if (s_self in syns or s_self == canon) and (s_other in syns or s_other == canon):
                return True
        return False


@dataclass
class CacheMissReport:
    missed: bool
    reason: str  # "TTL_EXPIRED", "MODEL_OR_KEY_CHANGED", "PREFIX_MUTATED", "FIRST_CALL", "NONE"
    missed_cost_usd: float  # Estimated wasted cache-write cost
    prev_cached_tokens: int
    curr_cached_tokens: int
    time_gap_ms: float
    root_cause: str = ""

    def __post_init__(self):
        if not self.root_cause:
            # Map canonical uppercase root-cause
            r_up = str(self.reason).upper()
            if "MODEL" in r_up:
                self.root_cause = "MODEL_OR_KEY_CHANGED"
            elif "TTL" in r_up:
                self.root_cause = "TTL_EXPIRED"
            elif "PREFIX" in r_up:
                self.root_cause = "PREFIX_MUTATED"
            elif "FIRST" in r_up:
                self.root_cause = "FIRST_CALL"
            else:
                self.root_cause = "NONE"


@dataclass
class _ContextState:
    last_cached_tokens: int = 0
    last_model: str = ""
    last_call_time: float = 0.0


class CacheMissDetector:
    """Tracks cache efficiency across consecutive LLM calls and flags financial waste."""

    def __init__(self, cache_ttl_ms: float = CACHE_TTL_MS):
        self.cache_ttl_ms = cache_ttl_ms
        self._states: Dict[str, _ContextState] = {}
        self._compacted_callers: set[str] = set()
        self._total_missed_cost: float = 0.0
        self._miss_count: int = 0
        self._call_count: int = 0

    def note_compaction(self, caller_id: str) -> None:
        """Records that compaction occurred for a caller/session, noting deliberate prefix mutation."""
        self._compacted_callers.add(caller_id)

    @property
    def _last_cached_tokens(self) -> int:
        return self._states.get("default", _ContextState()).last_cached_tokens

    @property
    def _last_model(self) -> str:
        return self._states.get("default", _ContextState()).last_model

    @property
    def _last_call_time(self) -> float:
        return self._states.get("default", _ContextState()).last_call_time

    def check(
        self,
        cached_tokens: int,
        cache_creation_tokens: int = 0,
        model: str = "",
        input_tokens: int = 0,
        context_key: str = "default",
    ) -> CacheMissReport:
        """Check if current call missed cache vs. previous call within the same context."""
        now = time.monotonic() * 1000.0
        state = self._states.setdefault(context_key, _ContextState())
        time_gap = (now - state.last_call_time) if state.last_call_time > 0 else 0.0
        self._call_count += 1

        if state.last_call_time == 0:
            report = CacheMissReport(
                missed=False,
                reason=CacheMissReason("first_call"),
                missed_cost_usd=0.0,
                prev_cached_tokens=0,
                curr_cached_tokens=cached_tokens,
                time_gap_ms=0.0,
                root_cause="FIRST_CALL",
            )
        elif cached_tokens == 0 and state.last_cached_tokens > 0:
            # Cache miss detected
            was_compacted = context_key in self._compacted_callers
            if was_compacted:
                self._compacted_callers.discard(context_key)
                reason = CacheMissReason("prefix_changed")
                root_cause = "PREFIX_MUTATED"
            elif model != state.last_model:
                reason = CacheMissReason("model_changed")
                root_cause = "MODEL_OR_KEY_CHANGED"
            elif time_gap > self.cache_ttl_ms:
                reason = CacheMissReason("ttl_expired")
                root_cause = "TTL_EXPIRED"
            else:
                reason = CacheMissReason("prefix_changed")
                root_cause = "PREFIX_MUTATED"

            # Estimate waste: cost of re-writing the cached tokens that were lost
            from monika.core.analytics.pricing import cost_usd

            missed_cost = cost_usd(
                model_name=state.last_model or model,
                input_tokens=state.last_cached_tokens,
                output_tokens=0,
                cached_tokens=0,
            )
            self._total_missed_cost += missed_cost
            self._miss_count += 1

            report = CacheMissReport(
                missed=True,
                reason=reason,
                missed_cost_usd=missed_cost,
                prev_cached_tokens=state.last_cached_tokens,
                curr_cached_tokens=cached_tokens,
                time_gap_ms=time_gap,
                root_cause=root_cause,
            )
            if missed_cost > 0.001:
                logger.warning(
                    f"[CacheMissDetector] Cache miss ({reason}): prev_cached={state.last_cached_tokens}, "
                    f"curr_cached={cached_tokens}, estimated_waste=${missed_cost:.4f}, "
                    f"time_gap={time_gap / 1000.0:.1f}s, model={model}, root_cause={root_cause}"
                )
            else:
                logger.info(
                    f"[CacheMissDetector] Cache miss ({reason}): prev_cached={state.last_cached_tokens}, "
                    f"curr_cached={cached_tokens}, estimated_waste=${missed_cost:.4f}, "
                    f"time_gap={time_gap / 1000.0:.1f}s, model={model}, root_cause={root_cause}"
                )
        else:
            report = CacheMissReport(
                missed=False,
                reason=CacheMissReason("none"),
                missed_cost_usd=0.0,
                prev_cached_tokens=state.last_cached_tokens,
                curr_cached_tokens=cached_tokens,
                time_gap_ms=time_gap,
                root_cause="NONE",
            )

        state.last_cached_tokens = cached_tokens
        state.last_model = model
        state.last_call_time = now
        return report

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_calls": self._call_count,
            "total_misses": self._miss_count,
            "miss_rate": round(self._miss_count / max(self._call_count, 1), 4),
            "total_missed_cost_usd": round(self._total_missed_cost, 6),
        }

    def reset(self):
        """Reset internal metrics."""
        self._states.clear()
        self._compacted_callers.clear()
        self._total_missed_cost = 0.0
        self._miss_count = 0
        self._call_count = 0


# Global singleton
global_cache_miss_detector = CacheMissDetector()
