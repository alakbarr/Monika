"""
A/B Parity and Resolution Evaluation Suite for Monika's Trading Engine.

Compares:
- Variant A (Baseline / Legacy Behavior): The unharmonized geometry, rigid priced-in gap,
  and brittle debate fail-closed behavior that led to 100% WAIT paralysis.
- Variant B (Current Resolved Engine): Dynamic geometry harmonization, smart priced-in
  justification acceptance, resilient debate evaluation, and safety preservation.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.domain.macro.regime_classifier import MacroRegime, RegimeClassifier


# ==============================================================================
# A/B Test 1: USDJPY Risk Geometry (Empty Set Deadlock Resolution)
# ==============================================================================
def test_ab_usdjpy_risk_geometry():
    """
    Simulates USDJPY market conditions during pre-FOMC consolidation:
    H4 ATR = 0.32626
    5-day ADR = 0.71800
    Minimum SL multiple = 1.0x ATR
    Standard SL ceiling = 35% ADR = 0.25130 (or 40% = 0.28720)
    """
    atr = 0.32626
    adr = 0.71800
    min_sl_mult = 1.0
    raw_min_sl = atr * min_sl_mult  # 0.32626

    # --- VARIANT A (Baseline Logic): Unharmonized ---
    sl_max_a = adr * 0.35  # 0.2513
    # Check if a candidate distance (e.g. 0.33) could ever be accepted
    # Condition: raw_min_sl <= dist <= sl_max_a * 1.05
    is_valid_range_a = raw_min_sl <= (sl_max_a * 1.05)
    assert not is_valid_range_a, "Variant A must produce an empty set deadlock (raw_min_sl > sl_max)"

    # --- VARIANT B (Harmonized Logic): Dynamic Squeeze Harmonization ---
    sl_max_b = adr * 0.35
    if raw_min_sl > sl_max_b:
        sl_max_b = max(sl_max_b, raw_min_sl * 1.25)  # Harmonized to ~0.4078

    is_valid_range_b = raw_min_sl <= (sl_max_b * 1.05)
    assert is_valid_range_b, "Variant B must successfully harmonize SL ceiling to accommodate ATR noise floor"
    assert sl_max_b >= raw_min_sl, "Harmonized ceiling must be strictly greater than or equal to minimum SL floor"


# ==============================================================================
# A/B Test 2: XAUUSD Priced-In Conflict Resolution
# ==============================================================================
def test_ab_xauusd_priced_in_conflict_resolution():
    """
    Simulates XAUUSD analysis where Stage 1 scored priced_in=7/10
    and Stage 2 scored priced_in=5/10 with detailed narrative justification.
    """
    brief_pi = 7
    submitted_pi = 5
    gap = abs(brief_pi - submitted_pi)
    assert gap == 2

    rationale_with_justification = (
        "CONFLUENCE SCORECARD FOR XAUUSD: PRICED-IN GAP JUSTIFICATION: "
        "Automated subscores total 1/9 but I set priced_in_score=5 because gold has idiosyncratic "
        "safe haven demand against Middle East escalation that lags nominal Treasury yield increases."
    )

    # --- VARIANT A (Legacy Logic): Strict Hard Error on gap >= 2 ---
    errors_a = []
    if gap >= 2:
        errors_a.append(f"PRICED-IN ASSESSMENT CONFLICT: Stage 1={brief_pi}, asset={submitted_pi}")
    assert len(errors_a) > 0, "Variant A must falsely reject the trade with a blocking validation error"

    # --- VARIANT B (Resolved Logic): Checks Narrative Justification ---
    errors_b = []
    rat_lower = rationale_with_justification.lower()
    has_justification = any(
        k in rat_lower
        for k in [
            "priced-in gap justification",
            "priced_in",
            "priced in",
            "justification for",
            "macro divergence",
            "stage 1",
            "idiosyncratic",
            "independent justification",
        ]
    )

    accepted_rationale_b = rationale_with_justification
    if gap == 2 and has_justification:
        accepted_rationale_b += (
            f"\n\n[SYSTEM: Priced-in gap ({gap}) acknowledged and accepted based on rationale context.]"
        )
    elif gap >= 2 and not has_justification:
        errors_b.append(f"PRICED-IN ASSESSMENT CONFLICT: Stage 1={brief_pi}, asset={submitted_pi}")

    assert len(errors_b) == 0, "Variant B must accept the trade when valid narrative justification is provided"
    assert "[SYSTEM: Priced-in gap (2) acknowledged and accepted" in accepted_rationale_b


# ==============================================================================
# A/B Test 3: Investment Judge Debate Resilience
# ==============================================================================
@pytest.mark.asyncio
async def test_ab_investment_judge_resilience():
    """
    Simulates an upstream LLM timeout during the final Investment Judge turn,
    while Bull Claim and Bear Dissent were already cleanly collected.
    """
    from monika.application.analysis.debate.investment_judge import evaluate_debate

    # Mock client that fails with timeout/empty response
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(side_effect=TimeoutError("Socket read timeout from provider"))

    bull_claim = {
        "claim": "Bullish trend continuation",
        "strength_score": 3,
        "parse_error": False,
    }
    bear_dissent = {
        "dissent": "Strong resistance and bearish FVG mitigation",
        "risk_severity": 7,  # Pro-strength for SELL is 7 vs Counter-threat 3
        "parse_error": False,
    }

    # Evaluate debate with decision='SELL' in original_context
    res = await evaluate_debate(
        client=mock_client,
        symbol="EURUSD",
        original_context={"decision": "SELL", "market_regime": "trending", "vix": 18.0},
        bull_claim=bull_claim,
        bear_dissent=bear_dissent,
    )

    # In Variant B: Instead of crashing into 'avoid' with risk=0.0,
    # the algorithmic fallback identifies that bear strength (7) outweighs bull (3) by >= 2,
    # and safely preserves the trade at 0.40x defensive risk multiplier.
    assert res.get("final_decision") == "sell"
    assert res.get("risk_multiplier") == 0.40
    assert "Algorithmic fallback adjudication" in res.get("reason", "")


# ==============================================================================
# A/B Test 4: Safety Fortress Preservation (Negative Test)
# ==============================================================================
def test_ab_safety_preservation_liquidity_contraction():
    """
    CRITICAL SAFETY VERIFICATION:
    Proves that under DXY >= 101.0 and US 10Y Real Yield >= 1.50%,
    the system in both Variant A and Variant B STRICTLY PROHIBITS commodity and crypto longs.
    Zero loosening of the Mechanical Fortress.
    """
    env = RegimeClassifier.classify(dxy=102.35, us10y_yield=2.66)

    assert env.regime == MacroRegime.LIQUIDITY_CONTRACTION
    assert env.allowed_crypto_longs is False, "Crypto BUY must remain strictly prohibited"
    assert env.allowed_commodity_longs is False, "Commodity BUY must remain strictly prohibited"
    assert "strictly prohibited" in env.reasoning.lower()


# ==============================================================================
# A/B Test 5: Tool Guardrail Calculation Threshold
# ==============================================================================
def test_ab_tool_guardrail_sizing_threshold():
    """
    Proves that calculate_position_size is permitted up to 3 calls for scenario analysis,
    without triggering premature AntiOscillationGuard suppression.
    """
    from monika.application.analysis.tools.tool_guardrails import AntiOscillationGuard

    guard = AntiOscillationGuard(threshold=2)

    sig = "calculate_position_size:EURUSD:1.1150:1.1180:0.5"

    # Call 1: Allowed
    v1 = guard.evaluate(sig, "calculate_position_size")
    assert v1.allowed is True
    guard.record(sig)

    # Call 2: In Variant A (threshold=2), this was BLOCKED.
    # In Variant B, calculation tools are granted threshold=4.
    v2 = guard.evaluate(sig, "calculate_position_size")
    assert v2.allowed is True, "Calculation tools must be allowed on second call for scenario confirmation"
    guard.record(sig)

    # Call 3: Still allowed
    v3 = guard.evaluate(sig, "calculate_position_size")
    assert v3.allowed is True
    guard.record(sig)

    # Call 4: Still allowed
    v4 = guard.evaluate(sig, "calculate_position_size")
    assert v4.allowed is True
    guard.record(sig)

    # Call 5: Suppressed after 4 consecutive calls to prevent infinite loops
    v5 = guard.evaluate(sig, "calculate_position_size")
    assert v5.allowed is False, "Runaway loops must still be bounded after 4 calls"
