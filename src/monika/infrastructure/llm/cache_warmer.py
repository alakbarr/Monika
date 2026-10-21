# ==============================================================================
# File: src/monika/infrastructure/llm/cache_warmer.py
# Description: Economic KV Prompt Cache Warmer.
# ==============================================================================

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger("Monika.LLM.CacheWarmer")

DEFAULT_CACHE_TTL_MS: float = 300_000.0  # 5 minutes in milliseconds
MIN_SAVINGS_THRESHOLD_USD: float = 0.05  # $0.05 minimum expected savings threshold


def get_cache_warming_delay_ms(ttl_ms: float) -> float:
    """
    Computes delay before cache warming dispatch:
    delay = max(1.0, min(ttl_ms * 0.9, ttl_ms - 10_000.0))
    Ensures warming triggers at 90% TTL or at least 10 seconds before expiration.
    """
    if ttl_ms <= 0:
        return 1.0
    return max(1.0, min(ttl_ms * 0.9, ttl_ms - 10_000.0))


def get_refresh_deadline_at_ms(next_warm_at_ms: float, ttl_ms: float, delay_ms: float) -> float:
    """Computes the hard deadline beyond which a scheduled warm is aborted as stale."""
    return next_warm_at_ms + (ttl_ms - delay_ms) / 2.0


def is_replayable(
    model_name: str,
    thinking_enabled: bool = False,
    adaptive_thinking: bool = False,
) -> bool:
    """
    Determines whether a model invocation can be safely replayed for cache warming.
    Models with unquantized dynamic thinking budgets or non-caching routes are rejected.
    """
    if not model_name or not isinstance(model_name, str):
        return False

    m_lower = model_name.lower()

    # Reject deprecated or non-caching mock/local stubs
    if "dummy" in m_lower or "mock" in m_lower:
        return False

    # Supported caching providers / models
    is_supported_family = any(
        fam in m_lower
        for fam in (
            "claude",
            "gemini",
            "gpt-4",
            "o1",
            "o3",
            "deepseek",
            "qwen",
        )
    )
    if not is_supported_family:
        return False

    # If thinking is enabled, only replay if adaptive or supported deterministic budget
    if thinking_enabled and not adaptive_thinking:
        # Anthropic Claude 3.7+ and Claude 4+ support adaptive thinking or quantized budgets
        if "claude" in m_lower and ("3-7" in m_lower or "3.7" in m_lower or "4" in m_lower):
            return True
        return False

    return True


def evaluate_warming_decision(
    prompt_tokens: int,
    warm_cost: float,
    miss_cost: float,
    phase: str = "active",
) -> Dict[str, Any]:
    """
    Evaluates whether warming the prompt cache is economically rational:
    expected_savings = continuation_probability * miss_cost - warm_cost >= $0.05
    """
    if prompt_tokens <= 0:
        return {
            "should_warm": False,
            "expected_savings": 0.0,
            "continuation_prob": 0.0,
            "warm_cost": warm_cost,
            "miss_cost": miss_cost,
            "threshold": MIN_SAVINGS_THRESHOLD_USD,
            "reason": "zero_tokens",
        }

    continuation_prob = 0.15 if str(phase).lower() == "idle" else 1.0
    expected_savings = (continuation_prob * miss_cost) - warm_cost
    should_warm = expected_savings >= MIN_SAVINGS_THRESHOLD_USD

    return {
        "should_warm": should_warm,
        "expected_savings": round(expected_savings, 6),
        "continuation_prob": continuation_prob,
        "warm_cost": round(warm_cost, 6),
        "miss_cost": round(miss_cost, 6),
        "threshold": MIN_SAVINGS_THRESHOLD_USD,
        "reason": "savings_above_threshold" if should_warm else "insufficient_expected_savings",
    }


class CacheWarmer:
    """
    Active economic prompt cache warmer.
    Schedules background minimal-cost requests to refresh prompt caches
    before the 5m or 1h TTL expires during active trading or multi-turn agent runs.
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        default_ttl_ms: float = DEFAULT_CACHE_TTL_MS,
    ):
        self.settings = settings or {}
        self.default_ttl_ms = default_ttl_ms
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._last_warmed_at: Dict[str, float] = {}

    def is_replayable(
        self,
        model_name: str,
        thinking_enabled: bool = False,
        adaptive_thinking: bool = False,
    ) -> bool:
        return is_replayable(model_name, thinking_enabled, adaptive_thinking)

    def evaluate_decision(
        self,
        prompt_tokens: int,
        warm_cost: float,
        miss_cost: float,
        phase: str = "active",
    ) -> Dict[str, Any]:
        return evaluate_warming_decision(prompt_tokens, warm_cost, miss_cost, phase)

    def schedule_warm(
        self,
        session_id: str,
        prompt_tokens: int,
        warm_cost: float,
        miss_cost: float,
        warm_coro_fn: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
        phase: str = "active",
        ttl_ms: Optional[float] = None,
    ) -> bool:
        """
        Schedules a background cache warming coroutine if economically rational.
        """
        decision = self.evaluate_decision(prompt_tokens, warm_cost, miss_cost, phase=phase)
        if not decision["should_warm"]:
            logger.debug(
                f"[CacheWarmer] Skipping warm for session '{session_id}': "
                f"expected_savings=${decision['expected_savings']:.4f} < ${MIN_SAVINGS_THRESHOLD_USD}"
            )
            return False

        if warm_coro_fn is None:
            logger.debug(f"[CacheWarmer] No warming callable provided for session '{session_id}'")
            return False

        # Cancel any pending timer for this session
        self.cancel_warm(session_id)

        eff_ttl = ttl_ms or self.default_ttl_ms
        delay_ms = get_cache_warming_delay_ms(eff_ttl)
        delay_sec = delay_ms / 1000.0

        async def _warm_runner():
            try:
                await asyncio.sleep(delay_sec)
                logger.info(
                    f"[CacheWarmer] Executing economic cache warm for session '{session_id}' "
                    f"(expected_savings=${decision['expected_savings']:.4f})"
                )
                await warm_coro_fn()
                self._last_warmed_at[session_id] = time.time()
            except asyncio.CancelledError:
                logger.debug(f"[CacheWarmer] Scheduled warm cancelled for session '{session_id}'")
            except Exception as e:
                logger.warning(f"[CacheWarmer] Cache warming execution failed for session '{session_id}': {e}")
            finally:
                self._active_tasks.pop(session_id, None)

        task = asyncio.create_task(_warm_runner())
        self._active_tasks[session_id] = task
        return True

    def cancel_warm(self, session_id: str) -> None:
        """Cancels a pending cache warming timer."""
        task = self._active_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def cancel_all(self) -> None:
        """Cancels all pending cache warming timers."""
        for session_id in list(self._active_tasks.keys()):
            self.cancel_warm(session_id)
