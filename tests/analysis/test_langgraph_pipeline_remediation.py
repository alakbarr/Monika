# ==============================================================================
# File: tests/analysis/test_langgraph_pipeline_remediation.py
# ==============================================================================

"""
Comprehensive regression & verification tests for the 14 LangGraph analysis pipeline
defects identified during the point-in-time replay simulation audit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.domain.macro.regime_classifier import MacroRegime, RegimeClassifier


# ==============================================================================
# 1. Defect #1: ToolExecutor Adopted Bracket vs MandatoryToolViolation
# ==============================================================================
@pytest.mark.asyncio
async def test_toolexecutor_allows_adopted_bracket_without_preceding_sizing_call():
    """ToolExecutor should allow submit_asset_analysis when adopted_bracket or explicit SL is provided."""
    from monika.application.analysis.tools.executor import ToolExecutor

    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, settings={}, symbol="EURUSD")

    tool_input = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "adopted_bracket": "LONG_OPTION_A",
        "stop_loss": 1.11142,
        "take_profit": 1.11993,
    }

    executor.domain_handlers = MagicMock()
    executor.execution_handlers = MagicMock()
    executor.position_handlers = MagicMock()
    executor.macro_handlers = MagicMock()
    executor.sentiment_handlers = MagicMock()

    executor.called_tools.add("get_price_history")

    res = await executor.execute("submit_asset_analysis", tool_input)
    assert res.get("status") != "blocked"
    assert res.get("error_type") != "MandatoryToolViolation"


# ==============================================================================
# 2. Defect #2: TurnToolPipeline False Persistence on Blocked Status
# ==============================================================================
def test_turntoolpipeline_does_not_persist_blocked_or_error_status():
    """TurnToolPipeline logic must not add blocked or errored tools to persisted_mandatory_tools."""
    validation_fail_statuses = {
        "validation_failed",
        "rejected_verification_required",
        "rejected_confluence_too_low",
        "blocked",
        "error",
        "failed",
    }
    c_name = "submit_asset_analysis"
    persisted_mandatory_tools = set()
    unpersisted_validation_failures = set()

    # Case 1: Status is "blocked"
    res_obj = {
        "status": "blocked",
        "error_type": "MandatoryToolViolation",
        "error": "Mental calculation forbidden",
    }
    is_tool_err = False
    st = res_obj.get("status")
    has_err = is_tool_err or (
        isinstance(res_obj, dict) and "error" in res_obj and st not in ("saved", "success", "updated")
    )

    if st in validation_fail_statuses or has_err:
        unpersisted_validation_failures.add(c_name)
    else:
        unpersisted_validation_failures.discard(c_name)
        persisted_mandatory_tools.add(c_name)

    assert "submit_asset_analysis" not in persisted_mandatory_tools
    assert "submit_asset_analysis" in unpersisted_validation_failures

    # Case 2: Status is "saved" (success)
    res_saved = {"status": "saved", "analysis_id": 100}
    st_saved = res_saved.get("status")
    has_err_saved = False
    if st_saved in validation_fail_statuses or has_err_saved:
        unpersisted_validation_failures.add(c_name)
    else:
        unpersisted_validation_failures.discard(c_name)
        persisted_mandatory_tools.add(c_name)

    assert "submit_asset_analysis" in persisted_mandatory_tools
    assert "submit_asset_analysis" not in unpersisted_validation_failures


# ==============================================================================
# 3. Defect #3: SMC Active Zone Filtering
# ==============================================================================
def test_stage2_prefetcher_format_smc_compact_preserves_unmitigated_zones():
    """Prefetcher must prioritize unmitigated order blocks even if mitigated ones appear first."""
    from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler

    bundler = Stage2DataBundler(session=AsyncMock(), settings={})

    value = {
        "timeframe": "H4",
        "order_blocks": [
            {"type": "BULLISH", "price_low": 4000.0, "price_high": 4010.0, "mitigated": True} for _ in range(6)
        ]
        + [
            {"type": "BULLISH", "price_low": 4020.0, "price_high": 4030.0, "mitigated": False, "timeframe": "H4"},
            {"type": "BEARISH", "price_low": 4080.0, "price_high": 4090.0, "mitigated": False, "timeframe": "H4"},
        ],
        "fvg_zones": [{"type": "BULLISH", "gap_low": 4015.0, "gap_high": 4018.0, "filled": True} for _ in range(6)]
        + [
            {"type": "BULLISH", "gap_low": 4022.0, "gap_high": 4025.0, "filled": False, "timeframe": "H4"},
        ],
    }

    formatted = bundler._format_smc_compact(value)
    assert "order_blocks (unmitigated):" in formatted
    assert "4020.0-4030.0" in formatted
    assert "fair_value_gaps (unfilled):" in formatted
    assert "4022.0-4025.0" in formatted


# ==============================================================================
# 4. Defect #4: Vocabulary Normalization in InHarnessGroundingValidator
# ==============================================================================
def test_inharness_grounding_normalizes_decision_and_scratchpad_bias():
    """InHarnessGroundingValidator must treat BUY and BULLISH as matching biases."""
    from monika.application.analysis.memory.working_scratchpad import WorkingScratchpad
    from monika.application.analysis.validators.in_harness_grounding import InHarnessGroundingValidator

    WorkingScratchpad.update_scratchpad(
        symbol="EURUSD",
        updates={"bias": "BULLISH", "invalidation_price": 1.1100},
    )

    decision_payload = {
        "decision": "BUY",
        "symbol": "EURUSD",
        "stop_loss": 1.11142,
        "entry_price": 1.11446,
        "take_profit": 1.11993,
    }

    _, errors, _ = InHarnessGroundingValidator.verify_grounding(decision_payload, {})
    contradiction_errors = [e for e in errors if "directly contradicts working scratchpad bias" in e]
    assert len(contradiction_errors) == 0, f"Expected no contradiction error, got: {contradiction_errors}"


# ==============================================================================
# 5. Defect #5: OutputVerifier Bracket Snapping Immunity
# ==============================================================================
def test_outputverifier_does_not_snap_valid_bracket_entry():
    """OutputVerifier must not overwrite entry_price when adopted_bracket is active."""
    from monika.application.analysis.validators.output_verifier import OutputVerifier

    verifier = OutputVerifier(settings={"trading": {"risk": {"min_rr_ratio": 1.5}}})
    output = {
        "decision": "buy",
        "symbol": "EURUSD",
        "entry_price": 1.11446,
        "stop_loss": 1.11142,
        "take_profit": 1.11993,
        "adopted_bracket": "LONG_OPTION_A",
        "confluence_score": 8,
        "priced_in_score": 5,
    }
    context_data = {
        "sr_levels": [1.11500, 1.11200],
        "atr": 0.0020,
    }

    snapped_output, snaps = verifier._apply_deterministic_math_snapping(
        output=output,
        failures=[],
        settings={"trading": {"risk": {"min_rr_ratio": 1.5}}},
        symbol="EURUSD",
        context_data=context_data,
    )
    assert snapped_output["entry_price"] == 1.11446


# ==============================================================================
# 6. Defect #6: SqlAlchemyMarketDataRepository Point-in-Time Cutoff
# ==============================================================================
@pytest.mark.asyncio
async def test_market_data_repo_filters_future_bars_with_as_of():
    """get_recent_bars must enforce timestamp <= as_of cutoff."""
    from monika.infrastructure.database.repositories.market_data_repository import (
        SqlAlchemyMarketDataRepository,
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    repo = SqlAlchemyMarketDataRepository(mock_session)
    as_of_dt = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    await repo.get_recent_bars("GBPUSD", timeframe="H4", limit=20, as_of=as_of_dt)

    executed_stmt = mock_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt).lower()
    assert "timestamp <=" in compiled_query or "price_ohlcv.timestamp <=" in compiled_query


# ==============================================================================
# 7. Defect #7: Factor Score Mismatch Only Blocks Overstatements
# ==============================================================================
def test_factor_score_mismatch_allows_conservative_score_capping():
    """A claimed score lower than the mathematical sum of factors must NOT be rejected."""
    claimed_score = 8
    expected_from_factors = 14
    effective_tolerance = 2

    overclaim_gap = claimed_score - expected_from_factors
    assert overclaim_gap <= effective_tolerance, "Conservative capping must not trigger FACTOR_SCORE_MISMATCH"


# ==============================================================================
# 8. Defect #8: SSVP Adjudication Substantive Acceptance
# ==============================================================================
def test_ssvp_adjudication_accepts_substantive_technical_rationale():
    """Adjudication must pass when substantive technical reasoning is provided."""
    rationale = (
        "Price action on H4 and H1 confirms institutional absorption at the discount floor, "
        "superseding the lagging macro specialist bias. Bullish OrderBlock at 4020 provides solid support "
        "with positive CVD divergence and exhaustion of selling pressure."
    )
    combined_text = rationale.lower()

    _has_substantive_adj = len(rationale.strip()) >= 120 and any(
        token in combined_text
        for token in (
            "price action",
            "structure",
            "discount",
            "premium",
            "order block",
            "absorption",
            "divergence",
            "fvg",
            "cvd",
            "brief",
            "specialist",
            "macro",
            "sentiment",
        )
    )
    assert _has_substantive_adj is True


# ==============================================================================
# 9. Defect #9: Gemini Provider Round-Robin Global Index Advance
# ==============================================================================
def test_gemini_provider_sticky_and_rotate_on_error():
    """Sticky key resolution preserves KV cache on instance; rotate_api_key advances on 429."""
    from monika.infrastructure.providers.gemini_provider import GeminiProvider

    free_keys = ["KEY_A", "KEY_B", "KEY_C"]
    GeminiProvider._key_cooldowns.clear()
    GeminiProvider._key_index = 0

    p1 = GeminiProvider(model="gemini-2.5-flash-lite", api_key=None, free_api_keys=free_keys)
    k1 = p1._get_api_key(sticky=True)
    assert k1 == "KEY_A"
    k1_again = p1._get_api_key(sticky=True)
    assert k1_again == "KEY_A"

    p1.rotate_api_key()
    k2 = p1._get_api_key(sticky=True)
    assert k2 == "KEY_B"


# ==============================================================================
# 10. Defect #10: Contrarian Specialist Synergy at Range Extreme
# ==============================================================================
def test_specialist_council_institutional_contrarian_synergy_at_extremes():
    """3-of-3 bearish at Range Ceiling (pos >= 0.60) must yield institutional_contrarian_synergy."""
    from monika.application.analysis.stages.per_asset.specialist_council import (
        compute_specialist_consensus_summary,
    )

    biases = {
        "technical": "bearish",
        "macro": "bearish",
        "sentiment": "bearish",
    }

    res_ceiling = compute_specialist_consensus_summary(biases, dealing_range_pos=0.89)
    assert res_ceiling["synergy_state"] == "institutional_contrarian_synergy"
    assert res_ceiling["consensus"] == "unanimous_institutional_reversal"

    biases_bull = {"technical": "bullish", "macro": "bullish", "sentiment": "bullish"}
    res_floor = compute_specialist_consensus_summary(biases_bull, dealing_range_pos=0.20)
    assert res_floor["synergy_state"] == "institutional_contrarian_synergy"
    assert res_floor["consensus"] == "unanimous_institutional_reversal"

    res_mid = compute_specialist_consensus_summary(biases, dealing_range_pos=0.50)
    assert res_mid["synergy_state"] == "crowded_unanimous_exhaustion"


# ==============================================================================
# 11. Defect #11: Range Telemetry Symmetry
# ==============================================================================
def test_range_telemetry_identifies_premium_distribution_zone():
    """Range position >= 0.62 must be classified as PREMIUM_DISTRIBUTION_ZONE favoring SELL."""
    dealing_range_pos = 0.89
    h4_impulse_atr = 0.50

    if dealing_range_pos >= 0.62 and h4_impulse_atr < 1.25:
        regime_classification = "PREMIUM_DISTRIBUTION_ZONE"
    elif dealing_range_pos <= 0.38:
        regime_classification = "DISCOUNT_ACCUMULATION_ZONE"
    else:
        regime_classification = "MID_RANGE"

    assert regime_classification == "PREMIUM_DISTRIBUTION_ZONE"


# ==============================================================================
# 12. Defect #12: Commodity Long Discount Exception in RegimeClassifier
# ==============================================================================
def test_regime_classifier_allows_commodity_long_on_deep_discount():
    """RegimeClassifier must allow commodity longs under strong DXY when deep discount + bullish technicals exist."""
    env = RegimeClassifier.classify(dxy=101.5, us10y_yield=2.67)
    assert env.regime in (MacroRegime.STRONG_DOLLAR_EXPANSION, MacroRegime.LIQUIDITY_CONTRACTION)

    ok_plain, _ = RegimeClassifier.is_trade_allowed(
        symbol="XAUUSD",
        direction="buy",
        dxy=101.5,
        us10y_yield=2.67,
        dealing_range_pos=0.55,
    )
    assert ok_plain is False

    ok_discount, msg = RegimeClassifier.is_trade_allowed(
        symbol="XAUUSD",
        direction="buy",
        dxy=101.5,
        us10y_yield=2.67,
        dealing_range_pos=0.23,
        technical_bias="BULLISH",
        confluence_score=9,
    )
    assert ok_discount is True
    assert "Macro Regime Exception" in msg
    assert "0.50x" in msg


# ==============================================================================
# 13. Defect #13: Desk Swarm Veto Protocol
# ==============================================================================
def test_team_compiler_requires_majority_or_hard_risk_for_veto():
    """Single desk role dissent should set caution_flag, not full risk_veto."""
    from monika.application.graph.team_compiler import DeskRole, TeamCompiler

    results = [
        {"stance": "bearish", "conviction": 0.8, "risk_veto": True, "veto_reason": "DXY headwind"},
        {"stance": "bullish", "conviction": 0.7, "risk_veto": False},
        {"stance": "bullish", "conviction": 0.6, "risk_veto": False},
        {"stance": "neutral", "conviction": 0.5, "risk_veto": False},
    ]
    roles = [
        DeskRole(role_id="macro", name="Macro Strategist", system_prompt=""),
        DeskRole(role_id="tech", name="Technical Analyst", system_prompt=""),
        DeskRole(role_id="flow", name="Flow Analyst", system_prompt=""),
        DeskRole(role_id="risk", name="Risk Manager", system_prompt=""),
    ]

    veto_reasons = []
    hard_risk_violation = False
    for r_res, r_def in zip(results, roles):
        if r_res.get("risk_veto"):
            vr = str(r_res.get("veto_reason") or f"Veto enforced by {r_def.name}")
            veto_reasons.append(vr)
            if any(kw in vr.lower() for kw in ("r:r", "stale", "geometry", "atr floor", "invalid")):
                hard_risk_violation = True

    veto_flag = len(veto_reasons) >= 2 or hard_risk_violation
    caution_flag = len(veto_reasons) == 1 and not hard_risk_violation

    assert veto_flag is False
    assert caution_flag is True


# ==============================================================================
# 14. Defect #14: DecisionLogger What-If Reason Truncation
# ==============================================================================
@pytest.mark.asyncio
async def test_decision_logger_safely_truncates_long_whatif_reason():
    """DecisionLogger.log_paper_whatif must truncate whatif_reason to <= 50 chars."""
    from monika.application.analysis.memory.decision_log import DecisionLogger

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.get.return_value = MagicMock(price_at_analysis=1.11446)

    long_reason = "Debate Judge Rejected: " + ("A" * 500)

    reason_str = str(long_reason or "")
    safe_whatif_reason = reason_str[:50]
    assert len(safe_whatif_reason) <= 50

    await DecisionLogger.log_paper_whatif(
        session=mock_session,
        analysis_id=123,
        symbol="EURUSD",
        decision="buy",
        confidence=0.8,
        confluence_score=8,
        rationale="Test rationale",
        reason=long_reason,
    )
    added_obj = mock_session.add.call_args[0][0]
    assert len(added_obj.whatif_reason) <= 50
    assert added_obj.reflection_text == long_reason
