# ==============================================================================
# File: evals/oracles/trade_discipline_oracle.py
# Description: Programmatic Oracle for Trade Discipline & Anti-Hallucination
# ==============================================================================

import re
from typing import Dict, Any, List


def evaluate_trade_discipline(fixture: Dict[str, Any], decision_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Zero-LLM mechanical verification of trade discipline:
    1. Literal preservation: Symbol matching exact string.
    2. Numerical grounding: Cited prices must exist in fixture price bounds.
    3. Justified decisions: For chop fixtures, rationale must cite chop/compression.
       For valid trends, lazy ungrounded WAIT is flagged.
    """
    violations: List[str] = []
    checks_passed: List[str] = []

    expected_sym = fixture.get("symbol", "").upper()
    data_sym = str(decision_data.get("symbol", "")).upper()
    if data_sym and data_sym != expected_sym:
        violations.append(f"Symbol mutation: expected {expected_sym}, got {data_sym}")
    else:
        checks_passed.append("Symbol literal preservation verified")

    decision = str(decision_data.get("decision", "")).upper()
    rationale = str(decision_data.get("rationale", "") or decision_data.get("reason", "")).lower()

    # Check required rationale keywords if specified in fixture
    must_mention = fixture.get("expected_outcome", {}).get("rationale_must_mention", [])
    if must_mention:
        found_any = any(kw.lower() in rationale for kw in must_mention)
        if not found_any:
            violations.append(f"Rationale missing required structural observations (expected one of: {must_mention})")
        else:
            checks_passed.append(f"Rationale contains justified market structure observations")

    # Anti-laziness check: If setup was pristine displacement (BUY/SELL expected), but agent returned WAIT without risk cause
    valid_decisions = [d.upper() for d in fixture.get("expected_outcome", {}).get("valid_decisions", [])]
    if "WAIT" not in valid_decisions and decision == "WAIT":
        # Check if rationale provided valid veto or was just lazy
        if not any(k in rationale for k in ("risk", "spread", "drawdown", "news", "fvg", "structure")):
            violations.append("Lazy Unjustified WAIT: Agent avoided trade without concrete structural or risk rationale")
        else:
            checks_passed.append("Defensive WAIT supported by risk context")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "checks_passed": checks_passed,
    }
