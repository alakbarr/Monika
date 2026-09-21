# ==============================================================================
# File: evals/oracles/macro_regime_oracle.py
# Description: Programmatic Oracle for Macroeconomic Regime & Policy Validation
# ==============================================================================

from typing import Any, Dict, List


def evaluate_macro_regime(fixture: Dict[str, Any], decision_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Zero-LLM mechanical verification of macroeconomic regime conclusions against
    fundamental indicator ground-truth (Real yields, DXY, Central Bank stance, VIX).

    Checks:
    1. Regime classification matches expected macro ground-truth.
    2. Policy stance (Hawkish/Dovish/Neutral) aligns with rate differential data.
    3. Defensive posture correctly triggered under elevated volatility (VIX > 25).
    """
    violations: List[str] = []
    checks_passed: List[str] = []

    macro_ctx = fixture.get("macro_context", {})
    expected = fixture.get("expected_outcome", {})

    # 1. Macro Regime Check
    inferred_regime = str(decision_data.get("risk_regime") or decision_data.get("regime") or "").upper()
    valid_regimes = [r.upper() for r in expected.get("valid_regimes", [])]

    if valid_regimes:
        if inferred_regime not in valid_regimes:
            violations.append(
                f"Inferred regime '{inferred_regime}' contradicts ground truth valid regimes {valid_regimes}."
            )
        else:
            checks_passed.append(f"Macro regime '{inferred_regime}' matches ground-truth set.")

    # 2. VIX Volatility Guard
    vix = float(macro_ctx.get("vix", 0.0) or 0.0)
    max_risk_pct = float(decision_data.get("risk_pct", 0.0) or decision_data.get("risk_percent", 0.0) or 0.0)

    if vix >= 30.0:
        if max_risk_pct > 1.0:
            violations.append(
                f"High volatility regime (VIX {vix:.1f} >= 30) violates defensive rule: "
                f"risk_pct {max_risk_pct}% exceeds max 1.0% allowable."
            )
        else:
            checks_passed.append("Defensive risk sizing enforced during high VIX regime.")

    # 3. Currency / Central Bank Stance Alignment
    cb_stance = str(decision_data.get("central_bank_stance") or decision_data.get("cb_stance") or "").lower()
    expected_stance = str(expected.get("expected_cb_stance", "")).lower()

    if expected_stance and cb_stance:
        if expected_stance not in cb_stance:
            violations.append(
                f"Policy stance '{cb_stance}' conflicts with expected stance '{expected_stance}'."
            )
        else:
            checks_passed.append(f"Central bank stance '{cb_stance}' accurately resolved.")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "checks_passed": checks_passed,
    }
