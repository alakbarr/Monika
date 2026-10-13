# ==============================================================================
# File: application/analysis/prefetch/news_digest/summaries.py
# ==============================================================================

"""
Deterministic macro/currency fallback summary generators and classification health reports.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import NewsItem
from monika.application.analysis.prefetch.news_digest.helpers import (
    _format_news_item_for_prompt,
    _jaccard_title_similarity,
)


def generate_deterministic_macro_summary(
    all_news: Sequence[Any],
    currency_signals_table: str = "",
    market_ctx: Optional[Dict[str, Any]] = None,
    macro_5d_context: str = "",
) -> str:
    """
    Deterministic rule-based macro overview fallback (H-7).
    Guarantees structured analytical brief even if LLM auxiliary provider times out, fails quota, or crashes.
    """
    ctx = market_ctx or {}
    vix_info = ctx.get("vix", {})
    vix_val = vix_info.get("value", 18.0) if isinstance(vix_info, dict) else 18.0
    dxy_info = ctx.get("dxy", {})
    dxy_trend = dxy_info.get("trend_5d", "neutral") if isinstance(dxy_info, dict) else "neutral"

    if isinstance(vix_val, (int, float)) and vix_val > 25.0:
        regime = "Risk-Off / High Volatility"
        regime_desc = f"Elevated market uncertainty with VIX at {vix_val:.1f}. Defensive positioning dominates."
    elif isinstance(vix_val, (int, float)) and vix_val < 15.0:
        regime = "Risk-On / Complacent"
        regime_desc = f"Low volatility regime with VIX at {vix_val:.1f}. Trend continuation and carry favored."
    else:
        regime = "Neutral / Moderate Volatility"
        regime_desc = f"Standard volatility conditions with VIX at {vix_val if isinstance(vix_val, (int, float)) else 'N/A'}. Localized catalysts active."

    # Extract high-impact items
    breaking_items = [n for n in all_news if getattr(n, "impact", "") == "BREAKING"]
    high_items = [n for n in all_news if getattr(n, "impact", "") == "HIGH"]
    top_items = (breaking_items + high_items)[:8]
    if not top_items:
        top_items = list(all_news)[:5]

    drivers_lines = []
    for item in top_items:
        title = (getattr(item, "title", "") or "Headline unavailable").strip()
        pub = getattr(item, "published_at", None)
        pub_str = pub.strftime("%H:%M UTC") if pub else "?"
        impact = getattr(item, "impact", "UNKNOWN")
        currencies = getattr(item, "currency_tags", "") or "GLOBAL"
        drivers_lines.append(f"- [{impact}] ({pub_str} | {currencies}) {title}")

    drivers_block = (
        "\n".join(drivers_lines) if drivers_lines else "- No breaking or high-impact news items recorded in window."
    )

    lines = [
        "**[MACRO REGIME]**",
        f"Regime: {regime}. {regime_desc} DXY 5-day trend is {dxy_trend}.",
        "",
        "**[KEY DRIVERS]**",
        drivers_block,
        "",
        "**[QUANTITATIVE CURRENCY SIGNALS]**",
        currency_signals_table or "No quantitative signals available.",
        "",
        "**[CROSS-CURRENCY IMPLICATIONS]**",
        f"USD direction is indicated as {dxy_trend}. Correlated asset movements should be evaluated against the quantitative table.",
        "",
        "> [!NOTE]",
        "> Generated via deterministic rule-based fallback (H-7) due to auxiliary LLM unavailability.",
        "*[deterministic_fallback: true]*",
    ]
    return "\n".join(lines)


def generate_deterministic_currency_summary(currency: str, items: Sequence[Any]) -> str:
    """
    Deterministic rule-based currency summary fallback (H-7).
    """
    if not items:
        return f"### {currency} Nuances\nNo significant news for {currency} in this period.\n*[deterministic_fallback: true]*"

    # Calculate net bias
    bullish_count = sum(1 for i in items if getattr(i, "sentiment", None) and f"BULLISH_{currency}" in i.sentiment)
    bearish_count = sum(1 for i in items if getattr(i, "sentiment", None) and f"BEARISH_{currency}" in i.sentiment)

    if bullish_count > bearish_count:
        bias = "BULLISH"
    elif bearish_count > bullish_count:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    lines = [
        f"### {currency} Nuances",
        f"1. **Current Bias**: {bias} (Rule-based: {bullish_count} bullish vs {bearish_count} bearish signals).",
        "2. **Key Nuances & Headlines**:",
    ]
    for it in list(items)[:5]:
        title = (getattr(it, "title", "") or "").strip()
        impact = getattr(it, "impact", "UNKNOWN")
        lines.append(f"   - [{impact}] {title}")

    lines.append("3. **Risk to Thesis**: New breaking headlines or unexpected macro data releases.")
    lines.append("*[deterministic_fallback: true]*")
    return "\n".join(lines)


async def get_classification_health_report(session) -> dict:
    """
    Compute classification health metrics untuk monitoring.
    Dipanggil dari dashboard atau daily report.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    from sqlalchemy import func, select

    from monika.infrastructure.database.models import NewsItem

    total = (
        await session.execute(select(func.count(NewsItem.id)).where(NewsItem.fetched_at >= since))
    ).scalar_one_or_none() or 0

    classified = (
        await session.execute(
            select(func.count(NewsItem.id)).where(NewsItem.fetched_at >= since).where(NewsItem.impact != None)
        )
    ).scalar_one_or_none() or 0

    by_impact = {}
    for impact in ["BREAKING", "HIGH", "MEDIUM", "LOW"]:
        count = (
            await session.execute(
                select(func.count(NewsItem.id)).where(NewsItem.fetched_at >= since).where(NewsItem.impact == impact)
            )
        ).scalar_one_or_none() or 0
        by_impact[impact] = count

    classification_rate = classified / total * 100 if total > 0 else 0
    breaking_rate = by_impact.get("BREAKING", 0) / classified * 100 if classified > 0 else 0

    return {
        "total_items_24h": total,
        "classified_count": classified,
        "classification_rate_pct": round(classification_rate, 1),
        "by_impact": by_impact,
        "breaking_rate_pct": round(breaking_rate, 1),
        "health": "good" if classification_rate > 80 else "degraded" if classification_rate > 50 else "critical",
        "anomaly_alert": breaking_rate > 30,  # Alert jika >30% BREAKING (likely over-classification)
    }
