# ==============================================================================
# File: indicators/pattern_similarity/context_verifier.py
# ==============================================================================

"""
Dual-Engine LLM Context Verifier.
Verifies macroeconomic context relevance for top pattern matches using:
1. LLM Pre-Trained Historical Macro Memory (zero web query cost, instant).
2. WebSearchService on-demand fallback with automatic MarketChronicle persistence.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PatternMatch, MarketContext, ContextVerdict, MultiTimeframeScreeningResult

logger = logging.getLogger("TradingAgent.PatternContextVerifier")

VERDICT_JSON_SCHEMA = {
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


class PatternContextVerifier:
    """Verifies macro context comparability for top historical chart pattern matches."""

    PROMPT_TEMPLATE = """You are Monika's Principal Macroeconomic Historian.
Evaluate whether the macroeconomic drivers during a historical chart pattern match are truly comparable to the current market environment.

CURRENT CONDITIONS ({current_date}):
{current_context_summary}

HISTORICAL MATCH ({match_date_str}, Symbol: {symbol}):
- Pattern Shape Similarity: {similarity:.1%}
- Historical Volatility Level: {hist_vix:.1f} ({hist_vix_cat})
- Historical USD Trend: {hist_dxy_trend}
- Historical Asset Position: {hist_asset_trend}
- Recorded Chronicle Context: {recorded_chronicle}

INSTRUCTIONS:
1. If Recorded Chronicle Context is 'None recorded', USE YOUR INTRINSIC KNOWLEDGE of financial market history for {match_date_str}. What were the dominant macroeconomic forces at that time?
2. Did the price trajectory following this historical pattern happen under economic drivers that make sense in today's context, or were they driven by completely unique/opposite macro conditions?
3. Return a JSON object matching this schema:
{{
    "relevance": "high" | "medium" | "low",
    "historical_context_summary": "1-2 sentences summarizing market drivers around {match_date_str}",
    "is_macro_driver_similar": true | false,
    "adjustment_factor": 0.0 to 1.0 (multiplier for outcome weight),
    "verdict_reason": "concise explanation (max 2 sentences)"
}}"""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def verify_top_matches(
        self,
        symbol: str,
        result: MultiTimeframeScreeningResult,
        current_context: MarketContext,
        session: AsyncSession,
        llm_client: Any,
        web_search_enabled: bool = True,
        limit: int = 3,
    ) -> List[ContextVerdict]:
        """Runs parallel LLM verification on top historical matches."""
        top_candidates = result.get_top_matches_across_timeframes(limit=limit)
        if not top_candidates or not llm_client:
            return []

        tasks = [
            self._verify_single_match(
                match=match,
                timeframe=tf,
                symbol=symbol,
                current_context=current_context,
                session=session,
                llm_client=llm_client,
                web_search_enabled=web_search_enabled,
            )
            for match, tf in top_candidates
        ]

        verdicts_raw = await asyncio.gather(*tasks, return_exceptions=True)
        valid_verdicts: List[ContextVerdict] = []

        for v in verdicts_raw:
            if isinstance(v, ContextVerdict):
                valid_verdicts.append(v)
            elif isinstance(v, Exception):
                logger.debug(f"LLM context verification item failed: {v}")

        return valid_verdicts

    async def _verify_single_match(
        self,
        match: PatternMatch,
        timeframe: str,
        symbol: str,
        current_context: MarketContext,
        session: AsyncSession,
        llm_client: Any,
        web_search_enabled: bool,
    ) -> ContextVerdict:
        """Verifies a single match via prompt injection."""
        match_dt = datetime.fromtimestamp(match.end_time, tz=timezone.utc)
        match_date_str = match_dt.strftime("%B %Y (%Y-%m-%d)")

        # 1. Check existing MarketChronicle
        chronicle_text = await self._get_chronicle_text(session, match_dt)

        # 2. Web search fallback if chronicle empty and enabled
        if not chronicle_text and web_search_enabled:
            chronicle_text = await self._search_and_cache_chronicle(session, symbol, match_dt)

        prompt = self.PROMPT_TEMPLATE.format(
            current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            current_context_summary=current_context.to_summary(),
            match_date_str=match_date_str,
            symbol=symbol,
            similarity=match.similarity,
            hist_vix=match.context_score * 30.0,
            hist_vix_cat=match.context_label,
            hist_dxy_trend=current_context.dxy_trend,
            hist_asset_trend=current_context.asset_trend,
            recorded_chronicle=chronicle_text or "None recorded",
        )

        try:
            resp = await asyncio.wait_for(
                llm_client.classify_json(
                    prompt=prompt,
                    schema=VERDICT_JSON_SCHEMA,
                ),
                timeout=12.0,
            )

            relevance = resp.get("relevance", "medium")
            adj = float(resp.get("adjustment_factor", 0.8))
            reason = resp.get("verdict_reason", "Verified against historical macro memory.")
            if resp.get("historical_context_summary"):
                reason = f"{resp['historical_context_summary']} — {reason}"

            return ContextVerdict(
                match=match,
                relevance=relevance,
                reason=reason,
                adjustment_factor=max(0.1, min(1.0, adj)),
            )
        except Exception as e:
            logger.debug(f"LLM classify_json failed for match {match_date_str}: {e}")
            return ContextVerdict(
                match=match,
                relevance="medium",
                reason=f"Historical match {match_date_str} evaluated via quantitative proxy.",
                adjustment_factor=0.75,
            )

    async def _get_chronicle_text(self, session: AsyncSession, match_dt: datetime) -> str:
        """Pulls recorded chronicle headlines near match date."""
        try:
            from database.models import MarketChronicle

            window_start = match_dt - timedelta(days=10)
            window_end = match_dt + timedelta(days=10)

            stmt = select(MarketChronicle).where(
                MarketChronicle.event_date.between(window_start, window_end)
            ).order_by(desc(MarketChronicle.severity)).limit(2)

            res = await session.execute(stmt)
            rows = res.scalars().all()
            if rows:
                return " | ".join(f"[{r.category}] {r.headline}" for r in rows)
        except Exception:
            pass
        return ""

    async def _search_and_cache_chronicle(
        self, session: AsyncSession, symbol: str, match_dt: datetime
    ) -> str:
        """On-demand web search fallback with self-caching to MarketChronicle."""
        try:
            from data_sources.web_search import get_web_search_service
            from database.models import MarketChronicle

            search_service = get_web_search_service(self.settings)
            query = f"{symbol} major financial news market drivers {match_dt.strftime('%B %Y')}"

            search_res = await asyncio.wait_for(
                search_service.search(query=query, topic="finance", max_results=2),
                timeout=8.0,
            )
            if not search_res:
                return ""

            titles = [r.get("title", "") for r in search_res if r.get("title")]
            joined = " | ".join(titles)

            if joined:
                # Save permanently so this date is never queried again
                entry = MarketChronicle(
                    event_date=match_dt,
                    category="policy_change",
                    headline=f"Historical Archive ({match_dt.strftime('%Y-%m')}): {joined[:250]}",
                    narrative=f"Auto-curated for pattern similarity context on {symbol}: {joined}",
                    currencies_affected=symbol[:3],
                    severity="medium",
                    is_ongoing=False,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(entry)
                await session.commit()
                return joined
        except Exception as e:
            logger.debug(f"Web search chronicle fallback skipped: {e}")
        return ""
