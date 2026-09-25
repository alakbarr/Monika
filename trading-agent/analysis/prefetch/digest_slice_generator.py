# ==============================================================================
# File: analysis/prefetch/digest_slice_generator.py
# ==============================================================================

"""
Digest Slice Generator: Rolling 2-hour window news digest synthesis.

Arsitektur:
1. Menyimpan snapshot berkala (NewsDigestSlice) setiap 2 jam dari berita terklasifikasi.
2. Menggabungkan 6 snapshot terakhir (12 jam) menjadi satu digest komprehensif
   dan berurutan secara kronologis untuk dikonsumsi Stage 1 Fundamental Analysis.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import NewsItem, NewsDigestSlice, NewsDigest, VIXData, DXYData
from analysis.providers.llm_factory import get_client_for_task
from analysis.prefetch.news_digest import _jaccard_title_similarity, _format_news_item_for_prompt

logger = logging.getLogger("TradingAgent.DigestSliceGenerator")

TARGET_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'XAU', 'XTI', 'BTC']
IMPACT_WEIGHT = {'BREAKING': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0, 'NONE': 0}


class DigestSliceGenerator:
    """Generates rolling 2-hour news digest slices and assembles 12-hour macro context."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._digest_generator = get_client_for_task('news_digest', self.settings)
        self._macro_synth = get_client_for_task('news_digest_macro_overview', self.settings)
        self._verifier = get_client_for_task('news_digest_verifier', self.settings)

    async def generate_slice(
        self,
        session: AsyncSession,
        period_start: datetime,
        period_end: datetime,
        trigger: str = 'scheduled',
    ) -> NewsDigestSlice:
        """
        Generate snapshot 2 jam untuk rentang period_start s/d period_end.
        """
        logger.info(f"[DigestSlice] Generating slice for window {period_start.isoformat()} to {period_end.isoformat()} (trigger={trigger})")

        # Query news items in window
        query = (
            select(NewsItem)
            .where(NewsItem.fetched_at >= period_start)
            .where(NewsItem.fetched_at <= period_end)
            .order_by(NewsItem.fetched_at.desc())
        )
        all_items = (await session.execute(query)).scalars().all()
        
        significant_items = [
            i for i in all_items 
            if i.impact in ('BREAKING', 'HIGH', 'MEDIUM')
        ]

        breaking_count = sum(1 for i in significant_items if i.impact == 'BREAKING')
        high_count = sum(1 for i in significant_items if i.impact == 'HIGH')

        # Group items by currency
        grouped_news: Dict[str, List[NewsItem]] = {c: [] for c in TARGET_CURRENCIES}
        for item in significant_items:
            if item.currency_tags:
                for tag in item.currency_tags.split(','):
                    clean_tag = tag.strip().upper()
                    if clean_tag in grouped_news:
                        grouped_news[clean_tag].append(item)

        # Build theme counts
        INTERNAL_TAGS = {'IRRELEVANT_PREFILTERED', 'DUPLICATE_PREFILTERED', 'IRRELEVANT', 'DUPLICATE'}
        theme_counts: Dict[str, int] = {}
        for item in significant_items:
            if item.sentiment:
                for s in item.sentiment.split(','):
                    clean_s = s.strip()
                    if clean_s and clean_s not in INTERNAL_TAGS:
                        theme_counts[clean_s] = theme_counts.get(clean_s, 0) + 1

        # Calculate weighted scores per currency
        weighted_scores: Dict[str, int] = {}
        for cur in TARGET_CURRENCIES:
            cur_items = grouped_news.get(cur, [])
            bull_w = sum(IMPACT_WEIGHT.get(i.impact or '', 1) for i in cur_items if i.sentiment and f'BULLISH_{cur}' in i.sentiment)
            bear_w = sum(IMPACT_WEIGHT.get(i.impact or '', 1) for i in cur_items if i.sentiment and f'BEARISH_{cur}' in i.sentiment)
            weighted_scores[cur] = bull_w - bear_w

        # Generate currency sections in parallel
        currency_sections: Dict[str, str] = {}
        tasks = []

        async def _synth_currency(cur: str, items: List[NewsItem]) -> tuple[str, str]:
            if not items:
                return cur, f"No high/medium impact developments in this 2-hour window."
            
            # Deduplicate items
            unique_items = []
            for it in items[:15]:
                if not any(_jaccard_title_similarity(it.title or '', u.title or '') > 0.6 for u in unique_items):
                    unique_items.append(it)

            news_text = '\n\n'.join([_format_news_item_for_prompt(it) for it in unique_items])
            prompt = f"""You are a senior macro trading analyst. Summarize {cur}-specific news from this 2-hour window.

{cur} NEWS:
<untrusted_news_data>
{news_text}
</untrusted_news_data>

Provide a concise 2-hour update:
1. **Bias**: Bullish/Bearish/Neutral based on data in this window
2. **Key Catalyst**: Specific figures/events reported
3. **Implication**: Short-term directional impact

Max 250 words. Be terse, factual, and strictly grounded in provided data."""
            try:
                use_top = any(getattr(i, 'impact', None) == 'BREAKING' for i in items) or cur in ('USD', 'XAU')
                client = self._macro_synth if use_top else self._digest_generator
                res = await client.generate(prompt)
                return cur, res or "Insufficient data."
            except Exception as e:
                logger.warning(f"[DigestSlice] Failed to synthesize {cur}: {e}")
                return cur, f"(Slice synthesis failed: {e})"

        for cur in TARGET_CURRENCIES:
            cur_items = grouped_news.get(cur, [])
            if cur_items or cur in ('USD', 'XAU'):
                tasks.append(_synth_currency(cur, cur_items))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, tuple) and len(res) == 2:
                    currency_sections[res[0]] = res[1]

        metadata_dict = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "items_in_window": len(all_items),
            "significant_items": len(significant_items),
            "breaking_count": breaking_count,
            "high_count": high_count,
            "weighted_scores": weighted_scores,
            "theme_counts": theme_counts,
        }

        period_hours = round((period_end - period_start).total_seconds() / 3600.0, 2)
        slice_entry = NewsDigestSlice(
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(timezone.utc),
            trigger=trigger,
            period_hours=period_hours,
            items_processed=len(all_items),
            breaking_count=breaking_count,
            high_count=high_count,
            currency_sections=json.dumps(currency_sections),
            metadata_json=json.dumps(metadata_dict),
        )
        session.add(slice_entry)
        await session.commit()

        logger.info(f"[DigestSlice] Saved slice #{slice_entry.id} ({period_hours}h, {breaking_count} BREAKING, {high_count} HIGH, {len(all_items)} items)")
        return slice_entry

    async def assemble_12h_digest(self, session: AsyncSession, hours_back: int = 12) -> Optional[str]:
        """
        Menggabungkan slices dalam window hours_back (default 12 jam) menjadi satu digest komprehensif.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        slices_query = (
            select(NewsDigestSlice)
            .where(NewsDigestSlice.period_end >= since)
            .order_by(NewsDigestSlice.period_start.asc())
        )
        slices = (await session.execute(slices_query)).scalars().all()

        if not slices:
            logger.info("[DigestSlice] No recent slices found. Triggering immediate slice generation...")
            now_utc = datetime.now(timezone.utc)
            start_utc = now_utc - timedelta(hours=2)
            try:
                fresh_slice = await self.generate_slice(session, start_utc, now_utc, trigger='on_demand')
                slices = [fresh_slice]
            except Exception as e:
                logger.error(f"[DigestSlice] On-demand slice generation failed: {e}")
                return None

        # Aggregate metrics across slices
        total_items = sum(s.items_processed or 0 for s in slices)
        total_breaking = sum(s.breaking_count for s in slices)
        total_high = sum(s.high_count for s in slices)

        # Aggregate net weighted scores per currency
        agg_weighted_scores: Dict[str, int] = {c: 0 for c in TARGET_CURRENCIES}
        agg_themes: Dict[str, int] = {}

        for s in slices:
            if s.metadata_json:
                try:
                    meta = json.loads(s.metadata_json)
                    for cur, score in meta.get("weighted_scores", {}).items():
                        agg_weighted_scores[cur] = agg_weighted_scores.get(cur, 0) + score
                    for th, cnt in meta.get("theme_counts", {}).items():
                        agg_themes[th] = agg_themes.get(th, 0) + cnt
                except Exception:
                    pass

        # Fetch market snapshot
        vix = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
        dxy_rows = (await session.execute(select(DXYData).order_by(DXYData.date.desc()).limit(5))).scalars().all()
        top_themes = sorted(agg_themes.items(), key=lambda x: x[1], reverse=True)[:5]

        # 1. Structured Metadata Block
        metadata_block = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_hours": hours_back,
            "slices_count": len(slices),
            "items_in_window_total": total_items,
            "breaking_count": total_breaking,
            "high_count": total_high,
            "market_snapshot": {
                "vix": vix.close if vix else None,
                "dxy_trend": ("strengthening" if len(dxy_rows) >= 2 and dxy_rows[0].close > dxy_rows[-1].close else "weakening") if dxy_rows else None,
                "dominant_themes": [t[0] for t in top_themes[:3]],
                "theme_counts": dict(top_themes[:5])
            },
            "priced_in_signal": {
                "high_saturation": [k for k, v in agg_themes.items() if v >= 6],
                "moderate_saturation": [k for k, v in agg_themes.items() if 3 <= v < 6],
                "saturation_risk": "HIGH" if sum(1 for v in agg_themes.values() if v >= 6) >= 2 else "MEDIUM" if any(v >= 6 for v in agg_themes.values()) else "LOW"
            }
        }

        digest_parts = [
            f"```digest_metadata\n{json.dumps(metadata_block, indent=2)}\n```\n"
        ]

        # 2. Aggregated Currency Signal Summary Table
        table_lines = [
            "### CURRENCY SIGNAL SUMMARY (12-Hour Aggregated, Impact-Weighted)\n",
            "| Currency | Dominant Signal | Confidence | 12h Net Score | Status |",
            "|----------|----------------|------------|---------------|--------|",
        ]
        for cur in TARGET_CURRENCIES:
            score = agg_weighted_scores.get(cur, 0)
            if score >= 4:
                sig, conf = "BULLISH", "HIGH" if score >= 8 else "MEDIUM"
            elif score <= -4:
                sig, conf = "BEARISH", "HIGH" if score <= -8 else "MEDIUM"
            elif score > 0:
                sig, conf = "MILDLY BULLISH", "LOW"
            elif score < 0:
                sig, conf = "MILDLY BEARISH", "LOW"
            else:
                sig, conf = "NEUTRAL", "MEDIUM"
            table_lines.append(f"| {cur} | {sig} | {conf} | {score:+d} | Active |")
        digest_parts.append("\n".join(table_lines))

        # 3. Macro Overview Synthesis
        macro_synth_prompt = f"""You are a senior macro trading strategist.
Based on {len(slices)} rolling news snapshot slices over the past {hours_back} hours, synthesize an authoritative MACRO OVERVIEW.

AGGREGATED DATA METRICS:
- Total news processed: {total_items}
- Breaking news: {total_breaking}, High impact: {total_high}
- VIX: {vix.close if vix else 'N/A'}, DXY trend: {metadata_block['market_snapshot']['dxy_trend']}
- Dominant Themes: {', '.join(t[0] for t in top_themes)}

CURRENCY 12H NET SCORES:
{json.dumps(agg_weighted_scores, indent=2)}

Provide:
1. **[MACRO REGIME]**: Current market regime & primary macroeconomic driver
2. **[THEME EVOLUTION]**: What storylines are escalating vs saturating across the 12h window
3. **[KEY DRIVERS]**: 2-3 primary catalysts dictating cross-asset sentiment
4. **[PRICED IN vs SURPRISE]**: What is fully priced in vs what could cause sudden market shocks
5. **[CROSS-CURRENCY IMPLICATIONS]**: Impact on USD, EUR, JPY, GBP, AUD, Gold (XAU), Oil (XTI), BTC

Strictly ground all numeric claims. Max 700 words."""

        try:
            macro_overview = await self._macro_synth.generate(macro_synth_prompt)
        except Exception as e:
            logger.error(f"[DigestSlice] Macro overview generation failed: {e}")
            macro_overview = None

        if not macro_overview or macro_overview.strip() == "" or macro_overview == "(Macro overview generation unavailable)":
            # Synthesize deterministic fallback from chronological slices or recent NewsDigest
            synth_parts = ["**Deterministic Macro Summary (Synthesized from Slices)**:"]
            for s in slices[-4:]:
                summary_text = getattr(s, 'macro_summary', None)
                if not summary_text and s.currency_sections:
                    try:
                        c_dict = json.loads(s.currency_sections)
                        highlights = [f"{cur}: {txt.strip()[:100]}" for cur, txt in c_dict.items() if txt and not txt.startswith("No high/medium")]
                        if highlights:
                            summary_text = "; ".join(highlights[:3])
                    except Exception:
                        pass
                if summary_text and not summary_text.startswith("("):
                    p_time = s.period_start.strftime("%H:%M")
                    synth_parts.append(f"- [{p_time} UTC]: {summary_text.strip()[:250]}")
            if len(synth_parts) > 1:
                macro_overview = "\n".join(synth_parts)
            else:
                recent_digest = (await session.execute(
                    select(NewsDigest).order_by(NewsDigest.generated_at.desc()).limit(1)
                )).scalar_one_or_none()
                if recent_digest and recent_digest.digest_text:
                    macro_overview = f"(Synthesized from recent NewsDigest):\n{recent_digest.digest_text[:500]}..."
                else:
                    macro_overview = "(Macro overview generation unavailable - relying on slice timeline below)"

        digest_parts.append("\n### MACRO OVERVIEW\n")
        digest_parts.append(macro_overview or "")

        # 4. 12-Hour Chronological Timeline (Slices)
        timeline_lines = [
            f"\n### 12-HOUR ROLLING TIMELINE ({len(slices)} Sequential Slices)\n"
        ]
        for idx, s in enumerate(slices, 1):
            p_start_str = s.period_start.strftime("%H:%M UTC")
            p_end_str = s.period_end.strftime("%H:%M UTC")
            timeline_lines.append(f"#### Window #{idx}: [{p_start_str} - {p_end_str}] (Breaking: {s.breaking_count}, High: {s.high_count}, Trigger: {s.trigger})")
            
            if s.currency_sections:
                try:
                    c_dict = json.loads(s.currency_sections)
                    for c_name, c_text in c_dict.items():
                        if c_text and not c_text.startswith("No high/medium"):
                            timeline_lines.append(f"**[{c_name}]**: {c_text.strip()}")
                except Exception:
                    pass
            timeline_lines.append("")

        digest_parts.append("\n".join(timeline_lines))

        # 5. Coverage Gap Check
        coverage_warning = await self._compute_coverage_gaps(session)
        if coverage_warning:
            digest_parts.append(f"\n### [COVERAGE GAPS]\n{coverage_warning}\n")

        full_digest = "\n\n".join(digest_parts)

        # Save assembled digest to news_digest table for legacy tools & caching
        try:
            entry = NewsDigest(
                generated_at=datetime.now(timezone.utc),
                period_hours=hours_back,
                digest_text=full_digest,
                items_processed=total_items,
            )
            session.add(entry)
            await session.commit()
        except Exception as e:
            logger.debug(f"[DigestSlice] Failed to save legacy NewsDigest record: {e}")

        return full_digest

    async def _compute_coverage_gaps(self, session: AsyncSession) -> str:
        """Cek aset utama yang absen dari data 12 jam terakhir."""
        since = datetime.now(timezone.utc) - timedelta(hours=12)
        missing = []
        for cur in TARGET_CURRENCIES:
            cnt = (await session.execute(
                select(func.count(NewsItem.id))
                .where(NewsItem.fetched_at >= since)
                .where(NewsItem.impact.in_(['BREAKING', 'HIGH', 'MEDIUM']))
                .where(NewsItem.currency_tags.contains(cur))
            )).scalar_one_or_none() or 0
            if cnt == 0:
                missing.append(cur)

        if not missing:
            return ""
        return (
            f"WARNING: No BREAKING, HIGH, or MEDIUM news detected in DB for {', '.join(missing)} in the last 12 hours. "
            "Stage 2 analysis for these assets will rely entirely on technicals and carry-over sentiment."
        )
