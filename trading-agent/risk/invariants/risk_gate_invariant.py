"""
Risk Gate Runtime Invariant Listener (Phase 5.6).
Enforces hard mathematical ceilings and non-negotiable risk constraints.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("TradingAgent.RiskInvariants")


class InvariantViolationError(RuntimeError):
    """Raised when a non-negotiable trading safety invariant is breached."""
    pass


def assert_risk_gate_invariants(
    proposal: Dict[str, Any],
    current_drawdown_pct: float,
    max_drawdown_limit: float = 3.0,
    min_rr_ratio: float = 1.0,
) -> None:
    """
    Asserts runtime risk invariants before order generation or risk-gate pass-through.
    Raises InvariantViolationError immediately on any breach.
    """
    # 1. Hard drawdown ceiling invariant
    if current_drawdown_pct > max_drawdown_limit:
        raise InvariantViolationError(
            f"Drawdown ceiling breach: current drawdown ({current_drawdown_pct:.2f}%) "
            f"exceeds hard limit ({max_drawdown_limit:.2f}%). Execution forbidden."
        )

    action = str(proposal.get("action", "")).lower()
    if action not in ("buy", "sell"):
        return  # Wait or hold proposals do not have order geometry

    entry = proposal.get("entry_price") or proposal.get("entry")
    sl = proposal.get("stop_loss") or proposal.get("sl")
    tp = proposal.get("take_profit") or proposal.get("tp")

    if entry is not None and sl is not None and tp is not None:
        try:
            e_val = float(entry)
            sl_val = float(sl)
            tp_val = float(tp)

            # 2. Strict order geometry invariant
            if action == "buy":
                if not (sl_val < e_val < tp_val):
                    raise InvariantViolationError(
                        f"Geometry breach for BUY: must satisfy SL ({sl_val}) < Entry ({e_val}) < TP ({tp_val})."
                    )
                risk = e_val - sl_val
                reward = tp_val - e_val
            else:  # sell
                if not (tp_val < e_val < sl_val):
                    raise InvariantViolationError(
                        f"Geometry breach for SELL: must satisfy TP ({tp_val}) < Entry ({e_val}) < SL ({sl_val})."
                    )
                risk = sl_val - e_val
                reward = e_val - tp_val

            # 3. Minimum mathematical Risk:Reward invariant
            if risk <= 0:
                raise InvariantViolationError(f"Invalid risk distance: {risk} <= 0.")
            rr = reward / risk
            if rr < min_rr_ratio:
                raise InvariantViolationError(
                    f"R:R invariant breach: calculated R:R ({rr:.2f}) < required min ({min_rr_ratio:.2f})."
                )
        except (ValueError, TypeError) as conv_err:
            raise InvariantViolationError(f"Corrupt numerical parameters in proposal: {conv_err}")


def check_risk_gate_invariant(context: Dict[str, Any]) -> Any:
    """
    InvariantRegistry adapter for risk gate invariant.
    Returns InvariantResult.
    """
    from .registry import InvariantResult, InvariantStatus

    proposal = context.get("proposal", {})
    current_drawdown_pct = float(context.get("current_drawdown_pct", 0.0))
    max_drawdown_limit = float(context.get("max_drawdown_limit", 3.0))
    min_rr_ratio = float(context.get("min_rr_ratio", 1.0))

    try:
        assert_risk_gate_invariants(
            proposal=proposal,
            current_drawdown_pct=current_drawdown_pct,
            max_drawdown_limit=max_drawdown_limit,
            min_rr_ratio=min_rr_ratio,
        )
        return InvariantResult(
            name="risk_gate",
            status=InvariantStatus.PASS,
            message="Risk gate invariants satisfied.",
            details={"drawdown": current_drawdown_pct, "max_limit": max_drawdown_limit},
            package_name="risk.invariants.risk_gate",
        )
    except InvariantViolationError as e:
        return InvariantResult(
            name="risk_gate",
            status=InvariantStatus.FAIL,
            message=str(e),
            details={"drawdown": current_drawdown_pct, "max_limit": max_drawdown_limit},
            package_name="risk.invariants.risk_gate",
        )

