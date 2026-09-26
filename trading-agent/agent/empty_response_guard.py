# ==============================================================================
# File: agent/empty_response_guard.py
# ==============================================================================

"""
Empty Response Guard & Cost-Aware Retry Controller.
Institutional-grade engine turn protection architecture.

1. Deterministic Empty Detection:
   Tracks consecutive empty (0 token or whitespace-only) responses from the same
   (model, provider, finish_reason) tuple. If 2 consecutive occur, short-circuits
   remaining retries and recommends immediate failover to secondary model.

2. Cost-Aware Retry Budget:
   If prompt input cost exceeds a specified monetary ceiling (default $0.25),
   clamps retry attempts from standard (e.g. 3) down to 1, preventing runaway
   financial waste when trading context windows (indicators, news, orderbook) are large.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.Agent.EmptyResponseGuard")

DEFAULT_COST_THRESHOLD_USD = 0.25
MAX_CONSECUTIVE_EMPTY_FOR_FAILOVER = 2


@dataclass
class EmptyRecoveryAction:
    """Action directive emitted by the 7-step empty response recovery ladder."""
    step: int
    action_type: str  # "nudge" | "close_reasoning" | "adjust_temp" | "prune_tools" | "retry" | "failover" | "terminal"
    instruction: str
    temperature_override: Optional[float] = None
    prune_tools: bool = False
    failover_model: Optional[str] = None


class EmptyResponseGuard:

    """Manages empty response state, consecutive empty tracking, and cost ceilings."""

    def __init__(self, cost_threshold_usd: float = DEFAULT_COST_THRESHOLD_USD):
        self.cost_threshold_usd = cost_threshold_usd
        # Key: (provider, model, finish_reason) -> count
        self._consecutive_empty_counts: Dict[Tuple[str, str, str], int] = {}

    def is_empty_response(self, content: Optional[str], token_count: int = 0) -> bool:
        """Determines if a model response is considered empty."""
        if content is None:
            return True
        if token_count == 0 and not content.strip():
            return True
        return not bool(content.strip())

    def record_empty_response(
        self,
        provider: str,
        model: str,
        finish_reason: str = "stop",
    ) -> int:
        """Records an empty response and returns current consecutive empty count."""
        key = (provider.lower(), model.lower(), finish_reason.lower())
        new_count = self._consecutive_empty_counts.get(key, 0) + 1
        self._consecutive_empty_counts[key] = new_count
        logger.warning(
            f"[EmptyResponseGuard] Empty response recorded for {provider}/{model} "
            f"(finish_reason={finish_reason}). Consecutive empty count: {new_count}"
        )
        return new_count

    def record_successful_response(self, provider: str, model: str):
        """Clears consecutive empty counts for the model upon successful non-empty response."""
        keys_to_clear = [
            k for k in self._consecutive_empty_counts
            if k[0] == provider.lower() and k[1] == model.lower()
        ]
        for k in keys_to_clear:
            self._consecutive_empty_counts.pop(k, None)

    def evaluate_retry_eligibility(
        self,
        provider: str,
        model: str,
        finish_reason: str,
        current_attempt: int,
        max_configured_retries: int = 3,
        estimated_input_cost_usd: float = 0.0,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether an empty response should be retried or if failover must be triggered.
        Returns: (should_retry, reason)
        """
        key = (provider.lower(), model.lower(), finish_reason.lower())
        consecutive_empty = self._consecutive_empty_counts.get(key, 0)

        # 1. Deterministic empty detection: 2 consecutive empty responses -> immediate failover
        if consecutive_empty >= MAX_CONSECUTIVE_EMPTY_FOR_FAILOVER:
            reason = (
                f"Deterministic empty response limit reached ({consecutive_empty} consecutive). "
                f"Triggering immediate provider/model failover."
            )
            logger.error(f"[EmptyResponseGuard] {reason}")
            return False, reason

        # 2. Cost-aware retry clamping
        effective_max_retries = max_configured_retries
        if estimated_input_cost_usd >= self.cost_threshold_usd:
            effective_max_retries = min(1, max_configured_retries)
            logger.info(
                f"[EmptyResponseGuard] High-cost prompt detected (${estimated_input_cost_usd:.4f} >= "
                f"${self.cost_threshold_usd:.2f}). Clamping empty retries to {effective_max_retries}."
            )

        if current_attempt >= effective_max_retries:
            reason = (
                f"Retry attempts exhausted ({current_attempt}/{effective_max_retries}) "
                f"under cost ceiling (${estimated_input_cost_usd:.4f})."
            )
            return False, reason

        return True, f"Eligible for retry ({current_attempt + 1}/{effective_max_retries})."

    def get_recovery_ladder_action(
        self,
        provider: str,
        model: str,
        attempt: int,
        raw_response: Optional[str] = None,
        task_role: Optional[str] = None,
    ) -> EmptyRecoveryAction:
        """
        Calculates the 7-step progressive recovery ladder action for empty turns:
          Step 1: System prompt formatting nudge
          Step 2: Close dangling reasoning block and prompt for output
          Step 3: Temperature laddering (adjust sampling temperature)
          Step 4: Tool schema simplification (drop auxiliary tools)
          Step 5: Clean provider retry
          Step 6: Role fallback model
          Step 7: Structured terminal emergency fallback
        """
        # Step 2 check: Dangling reasoning tag
        if raw_response and ("<think>" in raw_response and "</think>" not in raw_response):
            return EmptyRecoveryAction(
                step=2,
                action_type="close_reasoning",
                instruction="Your previous response closed inside a thinking block without public text. Please emit your final answer clearly outside tags.",
            )

        if attempt <= 1:
            return EmptyRecoveryAction(
                step=1,
                action_type="nudge",
                instruction="Your previous response was completely empty. Please proceed with your analysis or call the necessary tool directly.",
            )
        elif attempt == 2:
            return EmptyRecoveryAction(
                step=3,
                action_type="adjust_temp",
                instruction="Please provide your direct findings or action recommendation now.",
                temperature_override=0.2,
            )
        elif attempt == 3:
            return EmptyRecoveryAction(
                step=4,
                action_type="prune_tools",
                instruction="Please formulate your decision with primary tools.",
                prune_tools=True,
            )
        elif attempt == 4:
            return EmptyRecoveryAction(
                step=5,
                action_type="retry",
                instruction="Clean restart of model generation attempt.",
            )
        elif attempt == 5:
            return EmptyRecoveryAction(
                step=6,
                action_type="failover",
                instruction="Consecutive empty thresholds reached. Switching to fallback provider.",
            )
        else:
            return EmptyRecoveryAction(
                step=7,
                action_type="terminal",
                instruction="Terminal emergency fallback synthesized.",
            )

    def reset(self):
        """Reset all tracking counts."""
        self._consecutive_empty_counts.clear()


# Global singleton instance
global_empty_response_guard = EmptyResponseGuard()

