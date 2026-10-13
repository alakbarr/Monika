# ==============================================================================
# File: application/benchmark/task_specs/specialist_cases.py
# ==============================================================================

"""
Domain specialist (technical, sentiment, macro, pattern context) benchmark task specs.
"""

from __future__ import annotations

import json
from typing import Any

from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from monika.application.analysis.stages.per_asset_stage import (
    SPECIALIST_PROMPTS,
    SYMBOL_TO_COT,
    PerAssetStage,
    _render_specialist_prompt,
)
from monika.application.protocol.context_coherence import get_base_quote_tags

from ..fixture_loader import (
    get_golden_pattern_case,
    get_synthetic_sentiment_feed_payload,
    get_synthetic_stage2_bundle,
)
from .base import BenchmarkCase, _sym

_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "directional_bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "key_evidence": {"type": "array", "items": {"type": "string"}},
        "invalidation": {"type": "string"},
        "analysis": {"type": "string"},
    },
    "required": ["directional_bias", "confidence", "key_evidence", "invalidation", "analysis"],
}


async def _build_specialist_case(session: Any, settings: dict[str, Any], symbol: str, role: str) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    cot_code = SYMBOL_TO_COT.get(symbol, "")
    _text, raw = "", {}
    if not use_fixtures and session:
        try:
            bundled = await Stage2DataBundler(session, settings).fetch_bundle(symbol, cot_code=cot_code or None)
            _text, raw = bundled if isinstance(bundled, tuple) else ("", {})
        except Exception:
            pass
    if not raw:
        _, raw = get_synthetic_stage2_bundle(symbol)
    keys = PerAssetStage._SPECIALIST_KEY_MAP.get(role, [])
    view = {k: v for k, v in raw.items() if k in keys and v is not None} if isinstance(raw, dict) else {}
    if not view:
        view = raw
    data_view = json.dumps(view, default=str, indent=2) if view else "(no data available for this domain)"
    currencies = get_base_quote_tags(symbol).split(",")
    base_c = currencies[0].strip() if currencies else "USD"
    quote_c = currencies[1].strip() if len(currencies) > 1 else "USD"
    sysp = _render_specialist_prompt(SPECIALIST_PROMPTS[role], symbol, base_c, quote_c)
    return BenchmarkCase(
        symbol,
        "specialist",
        sysp,
        data_view,
        schema=_SPEC_SCHEMA,
        role_kwargs=dict(max_tokens=1400, thinking="low"),
        context_summary=data_view[:6000],
    )


async def _case_specialist_technical(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_specialist_case(session, settings, _sym(settings), "technical")


async def _case_specialist_sentiment(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_specialist_case(session, settings, _sym(settings), "sentiment")


async def _case_specialist_macro(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_specialist_case(session, settings, _sym(settings), "macro")


async def _case_sentiment_analyst(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    feed = get_synthetic_sentiment_feed_payload()
    prompt = (
        "Extract directional sentiment, positioning bias, and fear/greed score from the institutional commentary and positioning feed below.\n\n"
        f"{feed}\n\n"
        "Output structured JSON matching schema."
    )
    return BenchmarkCase(
        "sentiment_analyst",
        "specialist",
        system_prompt="You are a Sentiment and Positioning Specialist analyzing institutional flows, COT positioning, and retail sentiment extremes.",
        user_prompt=prompt,
        schema={
            "type": "object",
            "properties": {
                "sentiment_score": {"type": "number"},
                "bias": {"type": "string"},
                "institutional_positioning": {"type": "string"},
                "retail_crowd_risk": {"type": "string"},
            },
            "required": ["sentiment_score", "bias", "institutional_positioning"],
        },
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=feed[:4000],
    )


async def _case_pattern_context_verifier(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    pattern_data = get_golden_pattern_case()
    sym = pattern_data.get("symbol", "EURUSD")
    cur = pattern_data.get("current_conditions", {})
    hist = pattern_data.get("historical_match", {})
    prompt = f"""CURRENT CONDITIONS ({cur.get("date", "2026-10-01")}):
{cur.get("summary", "Fed hawkish at 3.75-4.00%, Middle East crude supply risk, DXY at 101.48, VIX at 16.7.")}

HISTORICAL MATCH ({hist.get("match_date", "2024-04-12")}, Symbol: {sym}):
- Pattern Shape Similarity: {hist.get("shape_similarity_pct", 84.5)}%
- Historical Volatility Level: {hist.get("hist_vix", 14.8)} ({hist.get("hist_vix_cat", "NORMAL")})
- Historical USD Trend: {hist.get("hist_dxy_trend", "BULLISH_REBOUND")}
- Historical Asset Position: {hist.get("hist_asset_trend", "BEARISH_CONTINUATION_BREAKDOWN")}
- Recorded Chronicle Context: {hist.get("recorded_chronicle", "")}

INSTRUCTIONS:
Evaluate whether macro drivers are comparable and output structured ContextVerdict JSON."""
    schema = {
        "type": "object",
        "properties": {
            "relevance": {"type": "string", "enum": ["high", "medium", "low"]},
            "historical_context_summary": {"type": "string"},
            "is_macro_driver_similar": {"type": "boolean"},
            "adjustment_factor": {"type": "number"},
            "verdict_reason": {"type": "string"},
        },
        "required": ["relevance", "is_macro_driver_similar", "adjustment_factor", "verdict_reason"],
    }
    return BenchmarkCase(
        "pattern_context_verifier",
        "specialist",
        system_prompt="You are Monika's Principal Macroeconomic Historian.",
        user_prompt=prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt,
    )
