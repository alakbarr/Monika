# ==============================================================================
# File: evals/oracles/smc_geometry_oracle.py
# Description: Programmatic Oracle for SMC Structural & Geometric Validation
# ==============================================================================

from typing import Dict, Any, List


def evaluate_smc_geometry(fixture: Dict[str, Any], decision_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Zero-LLM mechanical verification of SMC price geometry and risk-to-reward metrics.
    
    Checks:
    1. Direction and Level Alignment (BUY: TP > Entry > SL; SELL: TP < Entry < SL)
    2. R:R calculation must meet or exceed fixture.expected_outcome.min_rr (default 1.3)
    3. Structural placement: SL must protect beyond invalidation structure (OB/Swing)
    4. Minimum SL distance against ATR (prevent stop hunts / tight stops)
    """
    violations: List[str] = []
    checks_passed: List[str] = []
    
    decision = str(decision_data.get("decision", "")).upper()
    expected_decisions = [d.upper() for d in fixture.get("expected_outcome", {}).get("valid_decisions", [])]
    
    if decision not in expected_decisions:
        violations.append(f"Decision '{decision}' not in allowed set {expected_decisions}")
        return {
            "passed": False,
            "violations": violations,
            "checks_passed": checks_passed,
        }
        
    # If decision is WAIT/AVOID/REJECT, geometry checks do not apply
    if decision in ("WAIT", "AVOID", "REJECT"):
        checks_passed.append(f"Correctly chose defensive decision: {decision}")
        return {
            "passed": True,
            "violations": violations,
            "checks_passed": checks_passed,
        }

    raw_entry = decision_data.get("entry_price") or decision_data.get("entry") or fixture.get("current_price")
    raw_sl = decision_data.get("stop_loss") or decision_data.get("sl")
    raw_tp = decision_data.get("take_profit") or decision_data.get("tp")
    if raw_entry is None or raw_sl is None or raw_tp is None:
        violations.append("Invalid or missing numerical levels (entry/sl/tp)")
        return {
            "passed": False,
            "violations": violations,
            "checks_passed": checks_passed,
        }

    try:
        entry = float(raw_entry)
        sl = float(raw_sl)
        tp = float(raw_tp)
    except (ValueError, TypeError) as err:
        violations.append(f"Invalid or missing numerical levels (entry/sl/tp): {err}")
        return {
            "passed": False,
            "violations": violations,
            "checks_passed": checks_passed,
        }

    tech = fixture.get("technical_context") or {}
    atr = float(tech.get("atr_14") or 0.0)
    exp = fixture.get("expected_outcome") or {}
    min_rr = float(exp.get("min_rr") or 1.3)

    # 1. Directional sanity
    if decision == "BUY":
        if not (tp > entry > sl):
            violations.append(f"BUY directional violation: requires TP ({tp}) > Entry ({entry}) > SL ({sl})")
        else:
            checks_passed.append("BUY directional order valid")
    elif decision == "SELL":
        if not (tp < entry < sl):
            violations.append(f"SELL directional violation: requires TP ({tp}) < Entry ({entry}) < SL ({sl})")
        else:
            checks_passed.append("SELL directional order valid")

    # 2. Risk to Reward Ratio
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    if sl_dist <= 0:
        violations.append("Zero or negative Stop Loss distance")
    else:
        rr = round(tp_dist / sl_dist, 2)
        if rr < min_rr:
            violations.append(f"Calculated R:R {rr:.2f} violates minimum requirement {min_rr:.2f}")
        else:
            checks_passed.append(f"R:R ratio {rr:.2f} meets requirement (>={min_rr:.2f})")

    # 3. Structural SL bounds from fixture
    exp = fixture.get("expected_outcome", {})
    if "max_sl" in exp and sl > exp["max_sl"]:
        violations.append(f"SL ({sl}) exceeds maximum allowable structural SL ({exp['max_sl']})")
    elif "min_sl" in exp and sl < exp["min_sl"]:
        violations.append(f"SL ({sl}) violates minimum allowable structural SL ({exp['min_sl']})")
    else:
        checks_passed.append("SL respects fixture structural bounds")

    # 4. Minimum ATR buffer (SL distance >= 0.8x ATR)
    if atr > 0:
        min_sl_dist = 0.8 * atr
        if sl_dist < min_sl_dist:
            violations.append(f"SL distance ({sl_dist:.5f}) is too tight (< 0.8x ATR {min_sl_dist:.5f})")
        else:
            checks_passed.append(f"SL distance respects ATR buffer ({sl_dist:.5f} >= {min_sl_dist:.5f})")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "checks_passed": checks_passed,
    }
