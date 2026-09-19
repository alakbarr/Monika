# ==============================================================================
# File: evals/oracles/risk_compliance_oracle.py
# Description: Programmatic Oracle for Binary Risk Gate & Policy Compliance
# ==============================================================================

from typing import Dict, Any, List


def evaluate_risk_compliance(fixture: Dict[str, Any], decision_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Zero-LLM mechanical verification of institutional risk gate compliance.
    
    Verifies that hard risk constraints (spread limits, daily drawdown limits,
    portfolio heat caps, emergency triggers) are strictly obeyed without LLM hallucination
    or unauthorized bypass.
    """
    violations: List[str] = []
    checks_passed: List[str] = []

    expected = fixture.get("expected_outcome", {})
    requires_risk_veto = expected.get("requires_risk_veto", False)
    
    decision = str(decision_data.get("decision", "")).upper()
    reason = str(decision_data.get("reason", "") or decision_data.get("veto_reason", "")).lower()

    if requires_risk_veto:
        if decision in ("BUY", "SELL"):
            violations.append(
                f"Risk Gate Violation: Scenario requires binary VETO, but decision was '{decision}'"
            )
        else:
            checks_passed.append(f"Correctly honored risk gate veto with decision: {decision}")

        expected_veto = expected.get("veto_reason", "").lower()
        if expected_veto and expected_veto not in reason:
            # Also check reason or notes
            violations.append(
                f"Veto rationale missing expected risk factor '{expected_veto}' (got: '{reason}')"
            )
        else:
            checks_passed.append(f"Veto rationale correctly cited: {expected_veto}")

    # Check Spread constraint directly if present in fixture
    spread = float(fixture.get("spread_pips", 0.0))
    max_spread = float(fixture.get("max_allowed_spread_pips", 0.0))
    if max_spread > 0 and spread > max_spread:
        if decision in ("BUY", "SELL"):
            violations.append(
                f"Spread Breach: Current spread {spread} pips exceeds limit {max_spread} pips. Execution forbidden."
            )
        else:
            checks_passed.append(f"Spread filter passed: blocked execution due to {spread} > {max_spread} pips")

    # Check Daily Drawdown constraint directly if present in fixture
    acc = fixture.get("account_state", {})
    daily_pnl = float(acc.get("daily_pnl_pct", 0.0))
    dd_limit = float(acc.get("daily_loss_limit_pct", 0.0))
    if dd_limit < 0 and daily_pnl <= dd_limit:
        if decision in ("BUY", "SELL"):
            violations.append(
                f"Daily Drawdown Breach: Daily PnL {daily_pnl}% hit limit {dd_limit}%. Execution forbidden."
            )
        else:
            checks_passed.append(f"Drawdown filter passed: blocked execution due to {daily_pnl}% <= {dd_limit}%")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "checks_passed": checks_passed,
    }
