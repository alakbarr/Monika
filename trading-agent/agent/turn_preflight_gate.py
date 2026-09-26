# ==============================================================================
# File: agent/turn_preflight_gate.py
# ==============================================================================

"""
Turn Preflight Gate & Wall-Clock Budget Wrap-Up Controller.
Institutional-grade engine turn protection architecture.

1. Wall-Clock Budget Wrap-Up:
   Monitors execution elapsed time against a specified budget (e.g. 120s/180s).
   At 80% elapsed time, generates a RUN_BUDGET_WRAPUP_NOTICE injected into a safe
   cache-friendly context position, directing the model to conclude immediately.

2. Turn Preflight Gate:
   - Validates context floor requirements for tools & prompt schema.
   - Evaluates token pressure and detects insufficient compression progress,
     blocking pathological compression loops.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger("TradingAgent.Agent.TurnPreflightGate")

RUN_BUDGET_WRAPUP_NOTICE = (
    "[SYSTEM NOTICE - WALL-CLOCK BUDGET WRAP-UP]: You have consumed 80% of your allotted "
    "execution time budget. Do NOT initiate any new tool calls, web searches, or exploratory steps. "
    "Immediately synthesize and produce your final comprehensive response now."
)

DEFAULT_TURN_BUDGET_SECONDS = 120.0
DEFAULT_WRAPUP_RATIO = 0.80
MIN_LOCAL_CONTEXT_FLOOR_TOKENS = 4096


class WallClockBudgetManager:
    """Tracks turn elapsed time and generates wrap-up notices to ensure timely response."""

    def __init__(
        self,
        budget_seconds: float = DEFAULT_TURN_BUDGET_SECONDS,
        wrapup_ratio: float = DEFAULT_WRAPUP_RATIO,
    ):
        self.budget_seconds = budget_seconds
        self.wrapup_ratio = wrapup_ratio
        self.start_time: float = time.time()
        self._wrapup_injected: bool = False

    def reset(self, budget_seconds: Optional[float] = None):
        """Reset timer for a new turn."""
        if budget_seconds:
            self.budget_seconds = budget_seconds
        self.start_time = time.time()
        self._wrapup_injected = False

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.budget_seconds - self.elapsed_seconds)

    @property
    def is_expired(self) -> bool:
        return self.elapsed_seconds >= self.budget_seconds

    def should_inject_wrapup(self) -> bool:
        """True if budget >= wrapup_ratio (80%) and wrapup hasn't been injected yet."""
        if self._wrapup_injected:
            return False
        return self.elapsed_seconds >= (self.budget_seconds * self.wrapup_ratio)

    def mark_wrapup_injected(self):
        """Mark wrapup as delivered so it is not duplicated."""
        self._wrapup_injected = True
        logger.warning(
            f"[WallClockBudgetManager] Budget wrap-up triggered: {self.elapsed_seconds:.1f}s / "
            f"{self.budget_seconds:.1f}s elapsed ({self.elapsed_seconds / self.budget_seconds:.1%})."
        )

    def get_wrapup_notice(self) -> str:
        return RUN_BUDGET_WRAPUP_NOTICE


class TurnPreflightGate:
    """Validates model capabilities, token pressure, and context floors before API calls."""

    @staticmethod
    def validate_context_floor(
        context_window: int,
        estimated_required_tokens: int = MIN_LOCAL_CONTEXT_FLOOR_TOKENS,
    ) -> Tuple[bool, str]:
        """
        Validates whether the model's context window meets the minimal required floor.
        Prevents instant HTTP 400 Bad Request on small local model endpoints.
        """
        if context_window < estimated_required_tokens:
            msg = (
                f"Context floor violation: Model context window ({context_window}) is below "
                f"the minimum required threshold ({estimated_required_tokens}) for system prompts & tools."
            )
            logger.error(f"[TurnPreflightGate] {msg}")
            return False, msg
        return True, "Context floor OK"

    @staticmethod
    def calculate_token_pressure(
        estimated_prompt_tokens: int,
        context_window: int,
    ) -> float:
        """Returns token pressure ratio (0.0 - 1.0)."""
        if context_window <= 0:
            return 1.0
        return min(1.0, estimated_prompt_tokens / context_window)

    @staticmethod
    def compression_warrants_another_pass(
        tokens_before_compression: int,
        tokens_after_compression: int,
        min_reduction_ratio: float = 0.05,
    ) -> bool:
        """
        Detects insufficient compression progress to prevent infinite compression loops.
        Returns True only if compression achieved at least min_reduction_ratio (5%) reduction.
        """
        if tokens_before_compression <= 0:
            return False

        reduction = tokens_before_compression - tokens_after_compression
        ratio = reduction / tokens_before_compression

        if ratio < min_reduction_ratio:
            logger.warning(
                f"[TurnPreflightGate] Insufficient compression progress ({ratio:.1%} < {min_reduction_ratio:.1%}). "
                f"Tokens before={tokens_before_compression}, after={tokens_after_compression}. "
                f"Blocking recursive preflight compression pass."
            )
            return False

        logger.info(
            f"[TurnPreflightGate] Compression progress confirmed ({ratio:.1%} reduction, "
            f"saved {reduction} tokens)."
        )
        return True
