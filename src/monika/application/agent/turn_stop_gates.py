# ==============================================================================
# File: agent/turn_stop_gates.py
# ==============================================================================

"""
Turn Stop Verification Gates & Financial Risk Invariant Verification.
Enforces deterministic safety checks before allowing the agent to exit a turn loop.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Agent.TurnStopGates")


@dataclass
class StopGateContext:
    """Carries mutation and proposal context during turn execution."""
    turn_id: str
    mutated_files: List[str] = field(default_factory=list)
    has_unverified_file_edits: bool = False
    proposed_actions: List[Dict[str, Any]] = field(default_factory=list)
    has_unregistered_trade_proposals: bool = False
    pending_response: Optional[str] = None


class TradingRiskStopGate:
    """
    Deterministic gate ensuring no financial proposal or trading decision
    bypasses mandatory RiskGate and ApprovalHub registration.
    """

    _TRADE_INTENT_PATTERN = re.compile(
        r"\b(?:action:\s*['\"]?(?:buy|sell)|decision:\s*['\"]?(?:buy|sell)|place_order\b|close_position\b|execute_order\b|submitting (?:buy|sell) order|enter (?:long|short) position at \d)",
        re.IGNORECASE,
    )

    @classmethod
    def evaluate(cls, text: str, context: StopGateContext) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether the final response discusses placing trades without
        registering a formal pending proposal, and verifies proposal parameter integrity.
        """
        if not text and not context.proposed_actions:
            return True, None

        if context.has_unregistered_trade_proposals or (
            cls._TRADE_INTENT_PATTERN.search(text) and not context.proposed_actions
        ):
            return False, (
                "Financial Safety Invariant: You have articulated a trading action without registering "
                "it through 'propose_action' or RiskGate validation. You must formally submit "
                "the action proposal before concluding this turn."
            )

        if context.proposed_actions:
            for act in context.proposed_actions:
                if isinstance(act, dict) and act.get("action") in ("buy", "sell"):
                    entry = act.get("entry_price") or act.get("price")
                    sl = act.get("sl") or act.get("stop_loss")
                    tp = act.get("tp") or act.get("take_profit")
                    if entry is not None and sl is not None:
                        try:
                            e_val, sl_val = float(entry), float(sl)
                            if abs(e_val - sl_val) <= 1e-6:
                                return False, (
                                    f"Financial Safety Invariant: Proposed action on {act.get('symbol')} "
                                    "has invalid SL distance (0 or equal to entry price)."
                                )
                            if act.get("action") == "buy" and sl_val >= e_val:
                                return False, (
                                    f"Financial Safety Invariant: BUY proposal on {act.get('symbol')} "
                                    f"has SL ({sl_val}) above or at entry ({e_val})."
                                )
                            if act.get("action") == "sell" and sl_val <= e_val:
                                return False, (
                                    f"Financial Safety Invariant: SELL proposal on {act.get('symbol')} "
                                    f"has SL ({sl_val}) below or at entry ({e_val})."
                                )
                        except (ValueError, TypeError):
                            pass

        return True, None


class CodeVerifyStopGate:
    """
    Gate ensuring that code mutations are syntactically verified before turn completion.
    """

    @classmethod
    def evaluate(cls, context: StopGateContext) -> Tuple[bool, Optional[str]]:
        if context.has_unverified_file_edits and context.mutated_files:
            files_str = ", ".join(context.mutated_files[:3])
            return False, (
                f"Verification Invariant: Files ({files_str}) were modified during this turn. "
                "Please verify that the changes are syntactically valid and free of errors before finishing."
            )
        return True, None


def apply_stop_gates(
    final_text: str,
    context: StopGateContext,
) -> Tuple[bool, Optional[str]]:
    """
    Runs all stop gates in priority sequence. Returns (can_proceed, nudge_message).
    """
    # 1. Trading risk check has highest priority
    can_stop, msg = TradingRiskStopGate.evaluate(final_text, context)
    if not can_stop:
        logger.warning(f"[TurnStopGates] TradingRiskStopGate intercepted stop: {msg}")
        return False, msg

    # 2. Code verification check
    can_stop, msg = CodeVerifyStopGate.evaluate(context)
    if not can_stop:
        logger.warning(f"[TurnStopGates] CodeVerifyStopGate intercepted stop: {msg}")
        return False, msg

    return True, None
