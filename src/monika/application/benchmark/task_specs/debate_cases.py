# ==============================================================================
# File: application/benchmark/task_specs/debate_cases.py
# ==============================================================================

"""
Dialectical debate and adjudication benchmark task specs.
"""

from __future__ import annotations

import json
from typing import Any

from monika.application.analysis.debate.bear_analyst import generate_bear_dissent
from monika.application.analysis.debate.bull_analyst import generate_bull_advocacy
from monika.application.analysis.debate.fact_sheet import build_fact_sheet
from monika.application.analysis.debate.investment_judge import evaluate_debate

from ..db_access import entry_context, pick_asset_analysis
from ..fixture_loader import (
    get_golden_adjudication_case,
    get_golden_jev_debate_clash,
    get_synthetic_debate_claims,
    load_fixture_json,
)
from ..invoker import make_client
from .base import BenchmarkCase, _sym, logger


async def _get_debate_context(
    session: Any, settings: dict[str, Any], symbol: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    use_fixtures = settings.get("_use_fixtures", False)
    if not use_fixtures and session:
        try:
            analysis = await pick_asset_analysis(session, symbol)
            ctx = entry_context(analysis)
            fs = await build_fact_sheet(session, analysis.id)
            return ctx, fs
        except Exception:
            pass

    sym = (symbol or "EURUSD").upper()
    prod_fix = load_fixture_json(f"production_smc_snapshot_{sym.lower()}.json")
    price = prod_fix.get(
        "price",
        1.1377 if sym == "EURUSD" else (4260.50 if sym == "XAUUSD" else (158.80 if sym == "USDJPY" else 1.3217)),
    )
    tech = prod_fix.get("analysis", {})

    if sym == "EURUSD":
        decision = "BUY"
        entry_price = 1.1377
        stop_loss = 1.1340
        take_profit = 1.1460
        confluence_score = 11
        confluence_factors = ["BOS_BULLISH", "FVG_REBALANCE", "LONDON_SESSION_MOMENTUM"]
        rationale = "H1 Bullish Displacement with Order Block mitigation at 1.1350 and FVG fill."
        invalidation = "Break below swing low 1.1342"
    elif sym == "XAUUSD":
        decision = "BUY"
        entry_price = 4260.50
        stop_loss = 4248.00
        take_profit = 4290.00
        confluence_score = 12
        confluence_factors = ["ASIAN_LOW_SWEEP", "H1_ORDER_BLOCK", "INSTITUTIONAL_ABSORPTION", "SAFE_HAVEN_FLOW"]
        rationale = "Liquidity sweep below Asian session low ($4,252) followed by sharp bullish displacement and FVG confirmation."
        invalidation = "H1 close below $4,245"
    elif sym == "USDJPY":
        decision = "SELL"
        entry_price = 158.80
        stop_loss = 159.50
        take_profit = 157.20
        confluence_score = 10
        confluence_factors = ["H4_SUPPLY_REJECTION", "BOJ_NORMALIZATION", "BEARISH_DIVERGENCE"]
        rationale = "Rejection at key psychological resistance 159.20 with bearish order flow and BoJ yield pressure."
        invalidation = "H4 close above 159.60"
    elif sym == "GBPUSD":
        decision = "WAIT"
        entry_price = 1.3217
        stop_loss = 1.3180
        take_profit = 1.3320
        confluence_score = 6
        confluence_factors = ["RANGE_BOUND", "TRAPPED_VOLUME"]
        rationale = "Chop consolidation between 1.3190 and 1.3250 with extreme retail longing (83%). No clear edge."
        invalidation = "Break of range boundaries"
    elif sym == "BTCUSD":
        decision = "BUY"
        entry_price = 84200.0
        stop_loss = 83400.0
        take_profit = 85800.0
        confluence_score = 10
        confluence_factors = ["VWAP_RECLAIM", "FUNDING_RESET", "BULLISH_ORDER_FLOW"]
        rationale = "Reclaim of weekly anchored VWAP at $84,000 following weekend leverage flush."
        invalidation = "H1 close below $83,200"
    elif sym == "XTIUSD":
        decision = "BUY"
        entry_price = 95.80
        stop_loss = 94.20
        take_profit = 99.00
        confluence_score = 11
        confluence_factors = ["GEOPOLITICAL_SUPPLY_DISRUPTION", "H1_BOS", "INVENTORY_DRAW"]
        rationale = "Strait of Hormuz transit threat drives acute prompt backwardation and H1 structure breakout."
        invalidation = "Break below $93.80"
    else:
        decision = "BUY"
        entry_price = price
        stop_loss = round(price * 0.995, 5)
        take_profit = round(price * 1.012, 5)
        confluence_score = 9
        confluence_factors = ["STRUCTURE_BREAK", "FVG_FILL"]
        rationale = f"Structural setup on {sym} with favorable risk to reward."
        invalidation = f"Break below {price * 0.995:.5f}"

    ctx = {
        "symbol": sym,
        "decision": decision,
        "rationale": rationale,
        "confluence_score": confluence_score,
        "confluence_factors": confluence_factors,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "invalidation": invalidation,
    }
    fs = {
        "symbol": sym,
        "h1_structure": tech.get(
            "structure", "BULLISH" if decision == "BUY" else ("BEARISH" if decision == "SELL" else "CONSOLIDATION")
        ),
        "m15_structure": "BULLISH" if decision == "BUY" else ("BEARISH" if decision == "SELL" else "CHOP"),
        "key_support": stop_loss,
        "key_resistance": take_profit,
        "macro_bias": "Transatlantic divergence and Hormuz oil shock dictate directional positioning.",
    }
    return ctx, fs


async def _case_debate_bull(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    return BenchmarkCase(
        symbol,
        "debate",
        custom_fn=generate_bull_advocacy,
        custom_args=(symbol, ctx, fs),
        role_kwargs=dict(max_tokens=1500, thinking="medium"),
        context_summary=json.dumps({"context": ctx, "fact_sheet": fs}, default=str)[:5000],
    )


async def _case_debate_bear(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    use_fixtures = settings.get("_use_fixtures", False)
    bull_claim = None
    if not use_fixtures:
        try:
            ref_model = settings.get("_benchmark_reference_model") or "gemini-3.8-flash"
            ref = make_client(ref_model, settings, max_tokens=1500, thinking="medium")
            bull_claim = await generate_bull_advocacy(ref, symbol, ctx, fs)
        except Exception as e:
            logger.debug(f"Reference bull generation fallback to synthetic claims: {e}")
    if not bull_claim:
        bull_claim, _ = get_synthetic_debate_claims(symbol)

    return BenchmarkCase(
        symbol,
        "debate",
        custom_fn=generate_bear_dissent,
        custom_args=(symbol, ctx, bull_claim, fs),
        role_kwargs=dict(max_tokens=1500, thinking="medium"),
        context_summary=json.dumps({"context": ctx, "bull_claim": bull_claim, "fact_sheet": fs}, default=str)[:5000],
    )


async def _case_debate_judge(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    use_fixtures = settings.get("_use_fixtures", False)
    bull_claim, bear_dissent = None, None
    if not use_fixtures:
        try:
            ref_model = settings.get("_benchmark_reference_model") or "gemini-3.8-flash"
            ref = make_client(ref_model, settings, max_tokens=1500, thinking="medium")
            bull_claim = await generate_bull_advocacy(ref, symbol, ctx, fs)
            bear_dissent = await generate_bear_dissent(ref, symbol, ctx, bull_claim, fs)
        except Exception as e:
            logger.debug(f"Reference debate generation fallback to synthetic claims: {e}")
    if not bull_claim or not bear_dissent:
        syn_bull, syn_bear = get_synthetic_debate_claims(symbol)
        bull_claim = bull_claim or syn_bull
        bear_dissent = bear_dissent or syn_bear

    return BenchmarkCase(
        symbol,
        "debate",
        custom_fn=evaluate_debate,
        custom_args=(symbol, ctx, bull_claim, bear_dissent),
        role_kwargs=dict(max_tokens=800, thinking="high"),
        context_summary=json.dumps({"context": ctx, "bull": bull_claim, "bear": bear_dissent}, default=str)[:5000],
    )


_ADJUDICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "adjudication_rule_correctly_applied": {"type": "boolean"},
        "expected_outcome_per_rules": {"type": "string", "enum": ["buy", "sell", "wait", "avoid", "ambiguous"]},
        "mismatch_explanation": {"type": "string"},
        "verdict": {"type": "string", "enum": ["CONFIRM", "FLAG_FOR_REVIEW", "CONTRADICTS_OWN_FRAMEWORK"]},
    },
    "required": ["adjudication_rule_correctly_applied", "expected_outcome_per_rules", "verdict"],
}


async def _case_stage2_adjudicator(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    if use_fixtures:
        adj = get_golden_adjudication_case()
        symbol = adj.get("symbol", "USDJPY")
        biases_raw = adj.get("specialist_biases", {})
        biases = {k: v.get("bias", "NEUTRAL") for k, v in biases_raw.items()}
        confidences = {k: v.get("confidence", "MEDIUM") for k, v in biases_raw.items()}
        decision = "WAIT"
        rationale = f"{adj.get('conflict_description')} | Rules: {adj.get('adjudication_rules')}"
    else:
        biases = {"technical": "BULLISH", "sentiment": "BULLISH", "macro": "NEUTRAL"}
        confidences = {"technical": "HIGH", "sentiment": "MEDIUM", "macro": "LOW"}
        decision = "BUY"
        rationale = "High confidence bullish technical confluence aligns with sentiment."
        if session:
            try:
                analysis = await pick_asset_analysis(session, symbol)
                biases_row = json.loads(analysis.specialist_biases_json) if analysis.specialist_biases_json else {}
                biases = biases_row.get("biases", biases)
                confidences = biases_row.get("confidence", confidences)
                decision = analysis.decision or decision
                rationale = analysis.rationale or rationale
            except Exception:
                pass
    prompt = (
        "Rules: IF Technical=BULLISH AND Macro=BULLISH -> HIGH conf BUY. IF Technical=BEARISH AND "
        "Macro=BEARISH -> HIGH conf SELL. IF Technical vs Macro conflict -> WAIT unless technical "
        "trust_weight>0.8. IF all NEUTRAL/MIXED -> WAIT.\n\n"
        f"Specialist biases {symbol}: {json.dumps(biases)}\n"
        f"Specialist confidence: {json.dumps(confidences)}\n"
        f"Final decision: {decision}\nRationale: {rationale[:1500]}\n\n"
        "Did the final decision correctly follow the adjudication rules based on these specialist biases?"
    )
    return BenchmarkCase(
        symbol,
        "debate",
        "",
        prompt,
        schema=_ADJUDICATION_SCHEMA,
        role_kwargs=dict(max_tokens=800, thinking="medium"),
        context_summary=prompt,
    )


async def _case_jev_debate_evaluator(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    clash = get_golden_jev_debate_clash() if use_fixtures else {}
    state = {
        "symbol": clash.get("symbol", "EURUSD"),
        "bull_score": clash.get("bull_score", 8),
        "bear_score": clash.get("bear_score", 5),
        "bull_unmitigated_invalidation": clash.get("bull_unmitigated_invalidation", False),
        "bear_unmitigated_invalidation": clash.get("bear_unmitigated_invalidation", True),
        "bear_invalidation_detail": clash.get(
            "bear_invalidation_detail", "D1 close broke above 1.1050 invalidating bearish order block."
        ),
    }
    questions = [
        {
            "name": "winner",
            "type": "Choice",
            "options": ["bull", "bear", "deadlock"],
            "description": "Which debate persona holds the structurally superior thesis?",
        },
        {
            "name": "consensus_conviction",
            "type": "Score",
            "range": [1, 5],
            "description": "1: Ambiguous deadlock, 3: Clear edge, 5: Decisive refutation",
        },
    ]
    expected = {
        "winner": clash.get("expected_winner", "bull"),
        "consensus_conviction": clash.get("consensus_conviction", 4),
    }
    return BenchmarkCase(
        "jev_debate_evaluator",
        "debate",
        user_prompt="Arbitrate debate clash and determine winner based on structural refutations.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )
