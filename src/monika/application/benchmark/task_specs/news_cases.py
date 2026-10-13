# ==============================================================================
# File: application/benchmark/task_specs/news_cases.py
# ==============================================================================

"""
News classification, digest synthesis, consistency verification, and COT precompute task specs.
"""

from __future__ import annotations

import json
from collections import namedtuple
from typing import Any

from monika.application.analysis.prefetch.macro_preprocessor import MacroPreprocessor
from monika.application.analysis.prefetch.news_digest import (
    DIGEST_CONSISTENCY_SCHEMA,
    NEWS_CLASSIFICATION_SCHEMA,
    NewsDigestProcessor,
)

from ..db_access import latest_digest, recent_news
from ..fixture_loader import (
    get_golden_sentiment_matrix,
    get_synthetic_news_digest,
    get_synthetic_news_items,
)
from .base import BenchmarkCase


async def _get_news_items_list(session: Any, settings: dict[str, Any], limit: int = 25) -> list[Any]:
    use_fixtures = settings.get("_use_fixtures", False)
    bench_limit = settings.get("benchmark", {}).get("news_limit", limit)
    if not use_fixtures and session:
        try:
            items = await recent_news(session, limit=bench_limit)
            if items and len(items) >= min(10, bench_limit):
                return items
        except Exception:
            pass
    raw_fixtures = get_synthetic_news_items()
    NewsMock = namedtuple("NewsMock", ["title", "summary", "fetched_at", "impact"])
    items: list[Any] = []
    for item in raw_fixtures[:bench_limit]:
        items.append(
            NewsMock(
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                fetched_at=item.get("fetched_at", "2026-10-02T08:00:00Z"),
                impact=item.get("expected_impact", "HIGH"),
            )
        )
    return items


async def _case_news_classification(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=20)
    lines = [
        f"{i + 1}. TITLE: {n.title[:150]}\n   SUMMARY: {(n.summary or '')[:200]}\n   FETCHED: {n.fetched_at}"
        for i, n in enumerate(items)
    ]
    prompt = (
        "Classify market impact of each news item for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) trading "
        "(BREAKING/HIGH/MEDIUM/LOW/NONE), surprise_magnitude, currencies, sentiments.\n\n"
        + NewsDigestProcessor.CLASSIFICATION_FEW_SHOT_EXAMPLES
        + "\n\nITEMS:\n"
        + "\n".join(lines)
    )
    return BenchmarkCase(
        "news_batch",
        "news",
        "",
        prompt,
        schema=NEWS_CLASSIFICATION_SCHEMA,
        role_kwargs=dict(max_tokens=2000, thinking="medium"),
        context_summary=prompt[:5000],
    )


async def _case_news_classification_escalation(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=10)
    lines = [
        f"{i + 1}. ORIGINAL_VERDICT=HIGH\n   TITLE: {n.title[:200]}\n   FULL SUMMARY: {(n.summary or '')[:600]}"
        for i, n in enumerate(items)
    ]
    prompt = "Re-evaluate each item from SCRATCH, without bias toward original verdict.\n\nITEMS:\n" + "\n".join(lines)
    return BenchmarkCase(
        "news_escalation",
        "news",
        "",
        prompt,
        schema=NEWS_CLASSIFICATION_SCHEMA,
        role_kwargs=dict(max_tokens=2000, thinking="low"),
        context_summary=prompt[:5000],
    )


async def _case_news_classification_verifier(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=15)
    text = "\n\n".join(
        [f"{i + 1}. [current=HIGH] {n.title[:150]}\n   {(n.summary or '')[:200]}" for i, n in enumerate(items)]
    )
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "verdict": {
                    "type": "string",
                    "enum": ["CONFIRM", "PROMOTE_TO_HIGH", "DEMOTE_TO_MEDIUM", "DEMOTE_TO_LOW"],
                },
                "reason": {"type": "string"},
            },
            "required": ["index", "verdict", "reason"],
        },
    }
    prompt = (
        f"HIGH-vs-MEDIUM calibration editor. For each item decide if current tier is appropriate.\n\nITEMS:\n{text}"
    )
    return BenchmarkCase(
        "news_verifier",
        "news",
        "",
        prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=600, thinking="low"),
        context_summary=prompt[:4000],
    )


async def _case_news_digest(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=60)
    text = "\n\n".join([f"[{getattr(n, 'impact', 'HIGH')}] {n.title}\n{(n.summary or '')[:300]}" for n in items])
    prompt = (
        f"Synthesize the following news into a MACRO OVERVIEW for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) traders.\n\nNEWS:\n{text}\n\n"
        "Cover: [MACRO REGIME], [KEY DRIVERS], [WHAT MARKET IS WAITING FOR], "
        "[WHAT IS PRICED IN vs NOT], [CROSS-CURRENCY IMPLICATIONS]. Each claim MUST cite "
        "concrete numbers/levels/dates from the NEWS above."
    )
    return BenchmarkCase(
        "news_digest",
        "news",
        "",
        prompt,
        role_kwargs=dict(max_tokens=3000, thinking="medium"),
        context_summary=text[:5000],
    )


MACRO_OVERVIEW_STATIC_SYSTEM = """You are a senior macro trading analyst. Synthesize the following market news into a cohesive MACRO OVERVIEW for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) traders.

Your output MUST include these 6 sections:

**[MACRO REGIME]**
What is the current macro regime? (Risk-on/Risk-off/Stagflation/Disinflation/Uncertainty). Provide 2-3 sentences explaining the dominant macro theme. What changed from the previous digest?

**[5-DAY THEME EVOLUTION]**
Summarize how dominant themes evolved across the 5-day horizon. Which storylines are escalating (fresh catalysts / shocks) vs which are fading / saturating (narrative exhaustion / de-escalation relief)?

**[KEY DRIVERS]**
What are the 2-3 primary drivers moving markets right now? What is the market REACTING TO vs what is ALREADY PRICED IN?

**[WHAT MARKET IS WAITING FOR]**
List upcoming catalysts or data points the market is currently pricing/positioning for. Include: next major events, analyst consensus expectations, potential surprise scenarios.

**[WHAT IS PRICED IN vs NOT PRICED IN]**
Based on news narrative saturation, identify:
- What themes have been repeated 3+ days -> likely priced in (narrative exhaustion)
- What data/events are upcoming with uncertain outcomes -> potential surprise (fresh catalyst)
- What consensus expectations exist that could be "buy the rumor, sell the news"

**[CROSS-CURRENCY IMPLICATIONS]**
Based on the dominant USD theme, explain the cascading implications:
- If USD strengthens/weakens -> impact on EURUSD, GBPUSD, AUDUSD, USDJPY, XAUUSD
- Note any divergence from historical correlation patterns
- Identify which currency pairs are MOST affected by current news vs. LEAST affected

GROUNDING & ANTI-HALLUCINATION REQUIREMENT (MANDATORY):
1. CITE SPECIFIC NUMBERS ONLY FROM PROVIDED DATA: Every quantitative claim (price levels, %, bps, volumes, $, ¥, date) MUST be grounded directly in the NEWS or MARKET DATA CONTEXT provided in the user prompt.
2. STRICT PROHIBITION ON FABRICATED/PARAMETRIC NUMBERS: NEVER invent numbers, ETF flows, market caps, Treasury sizes, or central bank intervention figures from your pre-training memory. If a figure is not explicitly written in the provided text, DO NOT cite it.
3. QUALITATIVE FALLBACK: If a news driver contains no specific numeric statistics in the raw text, summarize the qualitative event and policy narrative accurately without inventing fake numbers."""


async def _case_news_digest_macro_overview(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=35)
    news_text = "\n\n".join([f"[{getattr(n, 'impact', 'HIGH')}] {n.title}\n{(n.summary or '')[:300]}" for n in items])
    macro_5d = (
        "5-DAY MACRO CONTEXT:\n"
        "- US: Non-farm payrolls blew out consensus (+265k vs +175k). Fed Chair Powell reiterates patient plateau at 3.75-4.00%.\n"
        "- Middle East: Naval conflict in Strait of Hormuz escalated, crude spikes to $106.40/bbl.\n"
        "- Eurozone: Flash CPI estimates show persistent energy-driven inflation at 3.2% while Germany factory orders decline -1.4%.\n"
        "- Japan: BoJ signals potential 25 bps rate hike at upcoming meeting, triggering JPY short covering."
    )
    quant_anchors = (
        "QUANTITATIVE ANCHORS:\n"
        "USD Bias: +0.85 (Strong Bullish) | EUR Bias: -0.75 (Strong Bearish) | JPY: +0.75 | XAU: +0.85\n"
        "DXY: 101.48 (+0.42%) | US 10Y Yield: 4.582% (+12.4 bps) | 10Y-2Y Spread: +34.1 bps | Brent Crude: $106.40/bbl"
    )
    user_prompt = f"""{macro_5d}

NEWS (sorted by recency and impact):
<untrusted_news_data>
{news_text}
</untrusted_news_data>

{quant_anchors}

Guidance: Synthesize all dominant drivers into a professional trading desk macro overview."""
    return BenchmarkCase(
        "news_digest_macro_overview",
        "news",
        system_prompt=MACRO_OVERVIEW_STATIC_SYSTEM,
        user_prompt=user_prompt,
        role_kwargs=dict(max_tokens=4000, thinking="high"),
        context_summary=user_prompt[:5000],
    )


async def _case_news_digest_verifier(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    digest_text = ""
    if not use_fixtures and session:
        try:
            digest = await latest_digest(session)
            if digest and digest.digest_text:
                digest_text = digest.digest_text
        except Exception:
            pass
    if not digest_text:
        digest_text = get_synthetic_news_digest()
    if not digest_text:
        digest_text = (
            "[MACRO REGIME] Hawkish rate plateau in US with Fed at 3.75-4.00% vs ECB at 2.50%.\n"
            "[KEY DRIVERS] Hormuz naval escalation pushing crude oil to $106/bbl.\n"
            "[CROSS-CURRENCY IMPLICATIONS] Strong USD tailwinds; EUR under pressure due to energy import drag."
        )
    prompt = (
        "Read this trading news digest and look for glaring contradictions between sections (quote "
        "verbatim both conflicting claims, rate severity material/minor).\n\nDIGEST:\n" + digest_text
    )
    return BenchmarkCase(
        "digest_verifier",
        "news",
        "",
        prompt,
        schema=DIGEST_CONSISTENCY_SCHEMA,
        role_kwargs=dict(max_tokens=800, thinking="low"),
        context_summary=digest_text[:6000],
    )


async def _case_cot_precompute(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    cot_signals = None
    if not use_fixtures and session:
        try:
            cot_signals = await MacroPreprocessor(settings=settings).compute_cot_signals(session)
        except Exception:
            cot_signals = None
    if not cot_signals:
        matrix_data = get_golden_sentiment_matrix()
        assets = matrix_data.get("assets", {})
        if assets:
            cot_signals = {
                sym: {
                    "non_commercial_bias": d.get("cot_institutional", {}).get("non_commercial_bias", "NEUTRAL"),
                    "net_position": d.get("cot_institutional", {}).get("net_position", 0),
                    "retail_contrarian": d.get("retail_fxssi", {}).get("contrarian_signal", "HOLD"),
                    "retail_long_pct": d.get("retail_myfxbook", {}).get("long_pct", 50.0),
                }
                for sym, d in assets.items()
            }
        else:
            cot_signals = {
                "EUR": {
                    "commercial_net": -45000,
                    "non_commercial_net": 38000,
                    "z_score": 1.45,
                    "bias": "BEARISH_EXTREME",
                },
                "USD": {
                    "commercial_net": 62000,
                    "non_commercial_net": -51000,
                    "z_score": -1.82,
                    "bias": "BULLISH_EXTREME",
                },
                "XAU": {
                    "commercial_net": -120000,
                    "non_commercial_net": 115000,
                    "z_score": 2.10,
                    "bias": "OVERBOUGHT_REVERSAL_RISK",
                },
            }
    prompt = (
        f"Computed COT and Institutional Positioning data:\n{json.dumps(cot_signals, indent=2)}\n\n"
        "Produce a 2-3 sentence summary of institutional positioning, highlighting extreme/"
        "overcrowded positions and reversal risk implications. Do not invent new figures."
    )
    return BenchmarkCase(
        "cot",
        "news",
        "You are a concise institutional positioning analyst.",
        prompt,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt,
    )
