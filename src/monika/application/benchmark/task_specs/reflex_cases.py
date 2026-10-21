# ==============================================================================
# File: application/benchmark/task_specs/reflex_cases.py
# ==============================================================================

"""
System One JEV reflexes, trade reflection, and harness auditing probes.
"""

from __future__ import annotations

import json
from typing import Any

from monika.application.analysis.memory.reflector import REFLECTION_SCHEMA, TradeReflector

from ..db_access import resolved_reflection
from ..fixture_loader import (
    get_golden_jev_confluence,
    get_golden_jev_timing,
    get_golden_trade_reflection,
    load_fixture_json,
)
from .base import BenchmarkCase


async def _case_trade_reflection(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    reflection = None
    enrichment = {}
    if not use_fixtures and session:
        try:
            reflection = await resolved_reflection(session)
            if reflection:
                enrichment = await TradeReflector(settings)._fetch_enrichment_context(session, reflection)
        except Exception:
            reflection = None
    if reflection is None:
        golden_ref = get_golden_trade_reflection()
        raw_pnl = golden_ref.get("outcome_pnl_usd")
        pnl = float(raw_pnl) if raw_pnl is not None else -280.0
        outcome_str = f"Outcome: {'Profitable' if pnl > 0 else 'Loss'} (${pnl:.2f})"
        exit_r = golden_ref.get("exit_reason") or "STOP_LOSS_HIT"
        holding = golden_ref.get("holding_hours") or 3.5
        dec = (golden_ref.get("decision") or "BUY").upper()
        sym = golden_ref.get("symbol") or "EURUSD"
        ref_text = (
            golden_ref.get("reflection_text")
            or "Stop loss placed too tight inside M15 liquidity pool rather than behind H4 structural swing low."
        )
        lesson = (
            golden_ref.get("lesson_crystallized") or "Always buffer Stop Loss beyond higher timeframe liquidity sweeps."
        )
        enrichment_data = {
            "symbol": sym,
            "vix_at_entry": 15.68,
            "vix_at_exit": 24.10,
            "historical_lesson": lesson,
            "post_mortem_notes": ref_text,
        }
        prompt = (
            f"Trade Rationale: {sym} {dec} at 1.1377 targeting 1.1460 based on H1 bullish displacement\n"
            f"Decision: {dec} (Confidence: 0.85)\n"
            f"{outcome_str}\n"
            f"Exit Reason: {exit_r}\n"
            f"Holding: {holding}h\n"
            f"Enrichment Data: {json.dumps(enrichment_data)}"
        )
        return BenchmarkCase(
            "golden_reflection_01",
            "reflection",
            "You are a trading post-mortem analyst. Use ONLY tags from enum. Concrete, not generic.",
            prompt,
            schema=REFLECTION_SCHEMA,
            role_kwargs=dict(max_tokens=1500, thinking="medium"),
            context_summary=prompt[:5000],
        )
    outcome_str = f"Outcome: {'Profitable' if reflection.was_profitable else 'Loss'} (${reflection.outcome_pnl_usd})"
    prompt = (
        f"Trade Rationale: {reflection.rationale_summary}\nDecision: {reflection.decision} "
        f"(Confidence: {reflection.confidence})\n{outcome_str}\nExit Reason: {reflection.exit_reason}\n"
        f"Holding: {reflection.holding_hours}h\nEnrichment Data: {json.dumps(enrichment, default=str)}"
    )
    return BenchmarkCase(
        str(reflection.id),
        "reflection",
        "You are a trading post-mortem analyst. Use ONLY tags from enum. Concrete, not generic.",
        prompt,
        schema=REFLECTION_SCHEMA,
        role_kwargs=dict(max_tokens=1500, thinking="medium"),
        context_summary=prompt[:5000],
    )


_HARNESS_HALLUCINATION_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions_detected": {"type": "array", "items": {"type": "string"}},
        "is_consistent": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "reasoning": {"type": "string"},
    },
    "required": ["contradictions_detected", "is_consistent", "severity", "reasoning"],
}


async def _case_harness_hallucination_detect(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    contradictory_brief = {
        "currency_bias": {"USD": "bullish", "EUR": "bullish", "AUD": "bullish"},
        "dxy_trend": "strengthening +1.2%",
        "vix": 34.5,
        "risk_sentiment": "risk-on",
        "treasury_10y_yield": "4.65% (rising)",
        "fedwatch_cut_prob": "92%",
    }
    prompt = (
        "Audit this macro brief data for internal contradictions and hallucination risks:\n\n"
        f"{json.dumps(contradictory_brief, indent=2)}\n\n"
        "Identify ALL contradictions (e.g. VIX > 30 vs risk-on, DXY rising vs EUR/AUD bullish simultaneously, "
        "yields rising vs 92% rate cut expectation). Output JSON matching schema."
    )
    return BenchmarkCase(
        "stage1_shadow_check",
        "macro",
        "You are an adversarial quantitative auditor detecting internal contradictions and hallucination risks.",
        prompt,
        schema=_HARNESS_HALLUCINATION_SCHEMA,
        role_kwargs=dict(max_tokens=600, thinking="medium"),
        context_summary=prompt,
    )


async def _case_harness_context_efficiency(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    from monika.infrastructure.llm.prompt_compressor import PromptBundleCompressor as ContextCompressor

    compressor = ContextCompressor(settings)
    raw_data = "Sample market structure text with extensive descriptions.\n" * 50
    compressed = compressor.compress_stage1_bundle(raw_data, max_tokens=200)
    prompt = (
        f"Analyze this compressed context and extract key market bias:\n\n{compressed}\n\n"
        "Provide a concise 1-paragraph summary with directional bias."
    )
    return BenchmarkCase(
        "news_digest",
        "macro",
        "You are a concise trading analyst.",
        prompt,
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=prompt,
    )


async def _case_harness_self_correction(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = (
        "The previous trading proposal for EURUSD had an invalid Stop Loss:\n"
        "- Proposed decision: BUY\n"
        "- Entry: 1.1000\n"
        "- Stop Loss: 1.1050 (ERROR: Stop loss is ABOVE entry for a BUY order)\n"
        "- Take Profit: 1.1100\n\n"
        "Correct this decision so that SL is strictly BELOW entry (e.g. 1.0950) and R:R >= 1.5."
    )
    return BenchmarkCase(
        "stage2_prescreen",
        "trade_decision",
        "You are a disciplined trade execution validator.",
        prompt,
        schema={
            "type": "object",
            "properties": {
                "decision": {"type": "string"},
                "entry": {"type": "number"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["decision", "entry", "stop_loss", "take_profit"],
        },
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=prompt,
    )


async def _case_jev_news_realtime(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    fix = load_fixture_json("s1_news_breaking_iran.json")
    state = fix.get(
        "state",
        {
            "title": "BREAKING: Iran IRGC launches cruise missile strike on oil tankers in Strait of Hormuz",
            "summary": "Three commercial crude oil tankers struck in the Strait of Hormuz. Brent crude surges +7.5% to $114/bbl.",
            "open_positions": ["XAUUSD", "EURUSD", "USDJPY"],
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "market_sentiment",
                "type": "Score",
                "range": [1, 5],
                "description": "1: Risk-off panic, 5: Risk-on euphoria",
            },
            {
                "name": "threatens_positions",
                "type": "Noul",
                "description": "Does headline introduce immediate sharp adverse volatility threat to open positions?",
            },
            {
                "name": "requires_circuit_breaker",
                "type": "Noul",
                "description": "Is this an extreme systemic shock requiring emergency circuit breaker or stop tightening?",
            },
        ],
    )
    expected = fix.get(
        "expected_answers",
        {
            "market_sentiment": 1,
            "threatens_positions": True,
            "threatens_positions_confidence_min": 0.85,
            "requires_circuit_breaker": True,
            "requires_circuit_breaker_confidence_min": 0.90,
        },
    )
    return BenchmarkCase(
        "jev_news_realtime",
        "news",
        user_prompt="Evaluate breaking news shock in real time against open positions.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_trigger_validator(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    fix = load_fixture_json("s1_trigger_stale_eurusd.json")
    state = fix.get(
        "state",
        {
            "symbol": "EURUSD",
            "trigger_type": "breakout_buy",
            "trigger_condition": {"level": 1.1460, "timeframe": "M15"},
            "current_price": 1.1377,
            "age_hours": 18.5,
            "macro_context": "Hawkish Fed hike + DXY break above 101.20 has shifted market structure to bearish H1.",
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "is_still_valid",
                "type": "Noul",
                "description": "Is this trade trigger still structurally valid and actionable given price action and elapsed time?",
            },
            {
                "name": "invalidation_risk",
                "type": "Score",
                "range": [1, 4],
                "description": "Rate risk that trigger is invalidated: 1: None, 2: Low, 3: Moderate, 4: High",
            },
        ],
    )
    expected = fix.get(
        "expected_answers", {"is_still_valid": False, "is_still_valid_confidence_min": 0.85, "invalidation_risk": 4}
    )
    return BenchmarkCase(
        "jev_trigger_validator",
        "trade_decision",
        user_prompt="Validate trade trigger validity against current price action.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_position_guard(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    fix = load_fixture_json("s1_position_guard_xauusd.json")
    state = fix.get(
        "state",
        {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 4275.00,
            "current_price": 4260.00,
            "sl": 4252.00,
            "tp": 4320.00,
            "volume": 0.5,
            "adverse_move_pips": 1500,
            "current_momentum": "sharp_bearish_impulse",
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "adverse_momentum",
                "type": "Noul",
                "description": "Is there strong adverse momentum against our BUY position in XAUUSD?",
            },
            {
                "name": "sl_threat_level",
                "type": "Score",
                "range": [1, 4],
                "description": "1: Safe, 2: Normal, 3: Elevated, 4: Critical",
            },
            {"name": "should_tighten_stop", "type": "Noul", "description": "Should trailing stop be tightened?"},
        ],
    )
    expected = fix.get(
        "expected_answers",
        {
            "adverse_momentum": True,
            "adverse_momentum_confidence_min": 0.85,
            "sl_threat_level": 4,
            "should_tighten_stop": True,
        },
    )
    return BenchmarkCase(
        "jev_position_guard",
        "risk",
        user_prompt="Evaluate position risk and adverse momentum in real time.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_exit_prescreen(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    fix = load_fixture_json("s1_exit_prescreen_gbpusd.json")
    state = fix.get(
        "state",
        {
            "symbol": "GBPUSD",
            "direction": "BUY",
            "entry_price": 1.3320,
            "sl": 1.3250,
            "tp": 1.3450,
            "current_price": 1.3217,
            "holding_hours": 14.2,
            "structural_breakdown": True,
            "adverse_move_pips": 103,
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "thesis_still_valid",
                "type": "Noul",
                "description": "Is original trading thesis still structurally valid?",
            },
            {
                "name": "exit_urgency",
                "type": "Score",
                "range": [1, 5],
                "description": "1: No urgency, 3: Moderate, 5: Critical",
            },
        ],
    )
    expected = fix.get(
        "expected_answers", {"thesis_still_valid": False, "thesis_still_valid_confidence_min": 0.90, "exit_urgency": 4}
    )
    return BenchmarkCase(
        "jev_exit_prescreen",
        "risk",
        user_prompt="Prescreen open position for early thesis invalidation exit.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_confluence_gate(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    confl = get_golden_jev_confluence() if use_fixtures else {}
    state = {
        "symbol": confl.get("symbol", "EURUSD"),
        "proposed_decision": "BUY",
        "confluence_score": confl.get("calculated_score", 8.4),
        "confluence_threshold": confl.get("threshold", 7.0),
        "factors": ["BOS_BULLISH", "FVG_DEMAND_BOUNCE", "H4_TREND_ALIGNED", "YIELD_SPREAD_SUPPORT"],
        "discrepancies": 0,
    }
    questions = [
        {
            "name": "pass_confluence",
            "type": "Noul",
            "description": "Does the trade proposal satisfy the required confluence threshold?",
        },
        {
            "name": "confluence_quality",
            "type": "Score",
            "range": [1, 5],
            "description": "1: Marginal, 3: Robust, 5: Pristine High-Conviction",
        },
    ]
    expected = {"pass_confluence": True, "pass_confluence_confidence_min": 0.90, "confluence_quality": 4}
    return BenchmarkCase(
        "jev_confluence_gate",
        "trade_decision",
        user_prompt="Evaluate trade confluence factors against structural gating threshold.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_session_timing_gate(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    t_state = get_golden_jev_timing() if use_fixtures else {}
    state = {
        "current_utc_hour": t_state.get("current_utc_hour", 14),
        "active_sessions": t_state.get("active_sessions", ["London", "New York"]),
        "is_overlap": t_state.get("is_overlap", True),
        "symbol": t_state.get("symbol", "EURUSD"),
        "near_tier1_event": t_state.get("near_tier1_event", False),
        "minutes_to_next_tier1": t_state.get("minutes_to_next_tier1", 180),
    }
    questions = [
        {
            "name": "timing_allowed",
            "type": "Noul",
            "description": "Is current session timing permissible for fresh order execution?",
        },
        {
            "name": "liquidity_tier",
            "type": "Score",
            "range": [1, 4],
            "description": "1: Illiquid off-peak, 2: Moderate Asian, 3: High single-session, 4: Peak London-NY overlap",
        },
    ]
    expected = {"timing_allowed": True, "timing_allowed_confidence_min": 0.95, "liquidity_tier": 4}
    return BenchmarkCase(
        "jev_session_timing_gate",
        "risk",
        user_prompt="Verify session timing and liquidity constraints before execution.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )
