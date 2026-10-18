"""
Risk Gate Runtime Invariant Listener (Phase 5.6).
Enforces hard mathematical ceilings and non-negotiable risk constraints.
"""

import logging
from typing import Any, Dict, Optional

from .registry import InvariantRegistry, InvariantResult, InvariantStatus, InvariantViolationError

logger = logging.getLogger("TradingAgent.RiskInvariants")


def assert_risk_gate_invariants(
    proposal: Any,
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

    # Support both TradeProposal object and dict
    if hasattr(proposal, "to_dict"):
        p_dict = proposal.to_dict()
    elif hasattr(proposal, "__dict__") and not isinstance(proposal, dict):
        p_dict = vars(proposal)
    elif isinstance(proposal, dict):
        p_dict = proposal
    else:
        p_dict = {}

    action = str(p_dict.get("action") or getattr(proposal, "direction", "") or p_dict.get("direction", "")).lower()
    if action not in ("buy", "sell"):
        return  # Wait or hold proposals do not have order geometry

    entry = (
        p_dict.get("entry_price")
        or p_dict.get("entry")
        or getattr(proposal, "entry_price", None)
        or getattr(proposal, "entry", None)
    )
    sl = (
        p_dict.get("stop_loss")
        or p_dict.get("sl")
        or getattr(proposal, "stop_loss", None)
        or getattr(proposal, "sl", None)
    )
    tp = (
        p_dict.get("take_profit")
        or p_dict.get("tp")
        or getattr(proposal, "take_profit", None)
        or getattr(proposal, "tp", None)
    )

    if entry is not None and sl is not None:
        try:
            e_val = float(entry)
            sl_val = float(sl)

            if e_val <= 0 or sl_val <= 0:
                raise InvariantViolationError(f"Entry ({e_val}) and SL ({sl_val}) must be positive.")

            # 2. Strict order geometry invariant for SL
            if action == "buy":
                if sl_val >= e_val:
                    raise InvariantViolationError(
                        f"Geometry breach for BUY: must satisfy SL ({sl_val}) < Entry ({e_val})."
                    )
                risk = e_val - sl_val
            else:  # sell
                if sl_val <= e_val:
                    raise InvariantViolationError(
                        f"Geometry breach for SELL: must satisfy SL ({sl_val}) > Entry ({e_val})."
                    )
                risk = sl_val - e_val

            if risk <= 0:
                raise InvariantViolationError(f"Invalid risk distance: {risk} <= 0.")

            # 3. If TP is provided, validate TP geometry and R:R ratio
            if tp is not None:
                tp_val = float(tp)
                if tp_val <= 0:
                    raise InvariantViolationError(f"TP ({tp_val}) must be positive.")

                if action == "buy":
                    if tp_val <= e_val:
                        raise InvariantViolationError(
                            f"Geometry breach for BUY: must satisfy Entry ({e_val}) < TP ({tp_val})."
                        )
                    reward = tp_val - e_val
                else:  # sell
                    if tp_val >= e_val:
                        raise InvariantViolationError(
                            f"Geometry breach for SELL: must satisfy TP ({tp_val}) < Entry ({e_val})."
                        )
                    reward = e_val - tp_val

                rr = reward / risk
                if rr < min_rr_ratio:
                    raise InvariantViolationError(
                        f"R:R invariant breach: calculated R:R ({rr:.2f}) < required min ({min_rr_ratio:.2f})."
                    )
        except (ValueError, TypeError) as conv_err:
            raise InvariantViolationError(f"Corrupt numerical parameters in proposal: {conv_err}")


def check_risk_gate_invariant(context: dict[str, Any]) -> Any:
    """
    InvariantRegistry adapter for risk gate invariant.
    Returns InvariantResult.
    """
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


InvariantRegistry.register_default_provider(lambda reg: reg.register("risk_gate_limits", check_risk_gate_invariant))
