# ==============================================================================
# File: application/analysis/prefetch/news_digest/macro_context.py
# ==============================================================================

"""
Macro context builder, calendar priors, and pre-filtering relevance checks.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Optional
import weakref

from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives.clock import ensure_utc
from monika.domain.market.news_impact_keywords import (
    HIGH_IMPACT_KEYWORDS,
    SHOCK_KEYWORDS,
)
from monika.infrastructure.database.models import NewsItem
from monika.application.analysis.prefetch.news_digest.base import (
    _NewsDigestMixinBase,
    logger,
)
from monika.application.analysis.prefetch.news_digest.helpers import (
    _jaccard_title_similarity,
)


_MACRO_CACHE_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()

_macro_context_cache: Optional[str] = None
_macro_context_cache_time: Optional[datetime] = None
_last_known_brief_id: Optional[int] = None
_last_known_breaking_id: Optional[int] = None


def get_macro_cache_lock() -> asyncio.Lock:
    """Return the event-loop-scoped lock serializing macro context cache operations."""
    loop = asyncio.get_running_loop()
    lock = _MACRO_CACHE_LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _MACRO_CACHE_LOCKS[loop] = lock
    return lock


def invalidate_global_macro_context_cache() -> None:
    """Explicitly invalidate global in-memory 5-day macro context cache across all instances."""
    global _macro_context_cache, _macro_context_cache_time, _last_known_brief_id, _last_known_breaking_id
    _macro_context_cache = None
    _macro_context_cache_time = None
    _last_known_brief_id = None
    _last_known_breaking_id = None


class MacroContextMixin(_NewsDigestMixinBase):
    """Mixin providing 5-day macro context, calendar impact priors, and headline relevance."""

    @property
    def _macro_context_cache(self) -> Optional[str]:
        return _macro_context_cache

    @_macro_context_cache.setter
    def _macro_context_cache(self, value: Optional[str]) -> None:
        global _macro_context_cache
        _macro_context_cache = value

    @property
    def _macro_context_cache_time(self) -> Optional[datetime]:
        return _macro_context_cache_time

    @_macro_context_cache_time.setter
    def _macro_context_cache_time(self, value: Optional[datetime]) -> None:
        global _macro_context_cache_time
        _macro_context_cache_time = value

    @property
    def _last_known_brief_id(self) -> Optional[int]:
        return _last_known_brief_id

    @_last_known_brief_id.setter
    def _last_known_brief_id(self, value: Optional[int]) -> None:
        global _last_known_brief_id
        _last_known_brief_id = value

    @property
    def _last_known_breaking_id(self) -> Optional[int]:
        return _last_known_breaking_id

    @_last_known_breaking_id.setter
    def _last_known_breaking_id(self, value: Optional[int]) -> None:
        global _last_known_breaking_id
        _last_known_breaking_id = value

    def invalidate_macro_context_cache(self) -> None:
        """Explicitly invalidate in-memory 5-day macro context cache across all instances."""
        invalidate_global_macro_context_cache()

    async def _build_7day_macro_grounding_context(self, session: AsyncSession, now_utc: datetime) -> str:
        """Membangun ringkasan narasi makro institusional dan grounding pasar yang komprehensif."""
        async with get_macro_cache_lock():
            return await self._build_7day_macro_grounding_context_locked(session, now_utc)

    async def _build_7day_macro_grounding_context_locked(self, session: AsyncSession, now_utc: datetime) -> str:
        """
        Membangun ringkasan narasi makro institusional dan grounding pasar yang komprehensif:
        1. Macro Core dari FundamentalBrief (Regime, Risk Sentiment, Biases, Priced-In Consensus, Invalidation).
        2. Kalender Ekonomi Berdampak Tinggi (HIGH) 7 hari ke depan (Immediate 24-48h vs Rest of Week).
        3. Riwayat Berita Berdampak Tinggi (HIGH + BREAKING) 7 hari terakhir dengan deduplikasi Jaccard.
        4. Kronik Makro Struktural 60 hari terakhir.
        Dilengkapi Hybrid Event-Driven Caching (TTL 60 menit + Reactive Invalidation).
        """
        from sqlalchemy import desc, select

        from monika.infrastructure.database.models import EconomicCalendar, FundamentalBrief, NewsItem

        # Check for reactive invalidation triggers (new brief or new breaking news)
        try:
            latest_brief_id = (
                await session.execute(
                    select(FundamentalBrief.id).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            latest_breaking_id = (
                await session.execute(
                    select(NewsItem.id)
                    .where(NewsItem.impact == "BREAKING")
                    .order_by(NewsItem.fetched_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            # If new event occurred since cache creation, invalidate immediately
            if (self._last_known_brief_id is not None and latest_brief_id != self._last_known_brief_id) or (
                self._last_known_breaking_id is not None and latest_breaking_id != self._last_known_breaking_id
            ):
                self.invalidate_macro_context_cache()

            self._last_known_brief_id = latest_brief_id
            self._last_known_breaking_id = latest_breaking_id
        except Exception:
            pass

        # Check in-memory TTL (up to 60 minutes)
        if self._macro_context_cache and self._macro_context_cache_time:
            if (now_utc - self._macro_context_cache_time).total_seconds() < 3600:
                return self._macro_context_cache

        try:
            # 1. Macro Core dari FundamentalBrief terbaru
            brief = (
                await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
            ).scalar_one_or_none()

            macro_core_lines = []
            if brief:
                regime = str(getattr(brief, "macro_regime", "mixed")).upper()
                risk = str(getattr(brief, "risk_sentiment", "mixed")).upper()
                cb = getattr(brief, "currency_bias", {}) or {}
                if isinstance(cb, dict) and cb:
                    bias_str = ", ".join([f"{k}:{v}" for k, v in cb.items() if v != "neutral"][:8])
                else:
                    bias_str = "Balanced"
                macro_core_lines.append(f"• REGIME & BIAS: Regime={regime} | Risk={risk} | Biases={bias_str}")

                s_json = getattr(brief, "structured_json", None)
                if s_json and isinstance(s_json, str):
                    try:
                        b_data = json.loads(s_json)
                        # Priced-in assessment
                        pi = b_data.get("priced_in_assessment", {})
                        if isinstance(pi, dict):
                            dom = pi.get("dominant_driver", "")
                            score = pi.get("priced_in_score", 5)
                            fw = pi.get("fedwatch_shift_summary", "")
                            unpriced = pi.get("key_unpriced_drivers", [])
                            if dom:
                                macro_core_lines.append(f"• PRICED-IN CONSENSUS (Score {score}/10): {dom}")
                            if fw:
                                macro_core_lines.append(f"• FEDWATCH / RATE EXPECTATIONS: {fw}")
                            if unpriced and isinstance(unpriced, list):
                                macro_core_lines.append(f"• KEY UNPRICED VULNERABILITY: {unpriced[0]}")

                        # Invalidation conditions
                        inv = b_data.get("invalidation_conditions", {})
                        if isinstance(inv, dict) and inv:
                            inv_sample = [f"{k}: {v[:90]}" for k, v in list(inv.items())[:3]]
                            macro_core_lines.append(f"• THESIS INVALIDATION THRESHOLDS: {' | '.join(inv_sample)}")

                        # Key upcoming risks
                        risks = b_data.get("key_upcoming_risks", [])
                        if isinstance(risks, list) and risks:
                            risk_strs = []
                            for r in risks[:3]:
                                if isinstance(r, dict):
                                    ev = r.get("event", "")
                                    tm = r.get("time", "")
                                    risk_strs.append(f"{ev} ({tm})")
                            if risk_strs:
                                macro_core_lines.append(f"• KEY MACRO RISKS MONITORED: {' | '.join(risk_strs)}")
                    except Exception as _b_err:
                        logger.debug(f"Failed to parse structured_json in brief: {_b_err}")
            else:
                macro_core_lines.append("• REGIME & BIAS: Regime=BALANCED | Risk=NEUTRAL | Biases=Balanced")

            macro_core_block = "\n".join(macro_core_lines)

            # 2. Upcoming High-Impact Economic Calendar (Next 7 Days)
            cal_stmt = (
                select(EconomicCalendar)
                .where(
                    EconomicCalendar.event_time >= now_utc,
                    EconomicCalendar.event_time <= now_utc + timedelta(days=7),
                    EconomicCalendar.impact.in_(["high", "HIGH"]),
                )
                .order_by(EconomicCalendar.event_time)
                .limit(16)
            )
            cal_rows = (await session.execute(cal_stmt)).scalars().all()

            imm_lines, week_lines = [], []
            cutoff_48h = now_utc + timedelta(hours=48)
            for c in cal_rows:
                if not c.event_time:
                    continue
                c_utc = ensure_utc(c.event_time) or c.event_time
                t_str = c_utc.strftime("%m-%d %H:%M UTC")
                fc_str = f"Forecast: {c.forecast}" if c.forecast else "No Frcst"
                pv_str = f"Prev: {c.previous}" if c.previous else "No Prev"
                line = f"• [{c.currency or 'MACRO'}] {c.event_name} ({t_str}) | {fc_str} | {pv_str}"
                if c_utc <= cutoff_48h:
                    imm_lines.append(line)
                else:
                    week_lines.append(line)

            cal_block = "[NEXT 24-48H IMMEDIATE CATALYSTS AWAITED]:\n" + (
                "\n".join(imm_lines) if imm_lines else "• No high-impact releases scheduled in next 48h."
            )
            if week_lines:
                cal_block += "\n[REST OF THE WEEK MAJOR RISK EVENTS]:\n" + "\n".join(week_lines[:5])

            # 3. 7-Day History of HIGH + BREAKING News (deduplicated)
            seven_days_ago = now_utc - timedelta(days=7)
            recent_high_items = (
                await session.execute(
                    select(NewsItem.title, NewsItem.currency_tags, NewsItem.impact, NewsItem.fetched_at)
                    .where(NewsItem.fetched_at >= seven_days_ago)
                    .where(NewsItem.impact.in_(["BREAKING", "HIGH"]))
                    .order_by(desc(NewsItem.fetched_at))
                    .limit(40)
                )
            ).all()

            theme_lines = []
            seen_titles = []
            for row in recent_high_items:
                t = row[0]
                if not t:
                    continue
                # Filter similar titles to keep the theme list compact and high-signal
                if any(_jaccard_title_similarity(t, st) > 0.40 for st in seen_titles):
                    continue
                seen_titles.append(t)
                cur = row[1] or "MACRO"
                imp = row[2]
                r_utc = ensure_utc(row[3]) if row[3] else None
                age_days = max(0, round((now_utc - r_utc).total_seconds() / 86400, 1)) if r_utc else 0
                theme_lines.append(f"• [{cur}] ({imp}, {age_days}d ago): {t[:110]}")
                if len(theme_lines) >= 12:
                    break

            themes_block = (
                "\n".join(theme_lines) if theme_lines else "• No dominant multi-day shock recorded in recent 7 days."
            )

            # 4. SOTA Memory Grounding: Active structural chronicles (ongoing wars, central bank leadership, tariffs)
            chronicle_block = ""
            try:
                from monika.application.analysis.memory.chronicle_writer import ChronicleWriter

                c_writer = ChronicleWriter(self.settings)
                c_bullets = await c_writer.get_condensed_chronicle_bullets(session, days_back=60, limit=5)
                if c_bullets:
                    chronicle_block = (
                        f"ACTIVE STRUCTURAL MACRO REGIMES (Ongoing Historical Milestones & Conflicts):\n{c_bullets}\n\n"
                    )
            except Exception as _c_err:
                logger.debug(f"Failed to fetch chronicle in news context: {_c_err}")

            context = (
                f"=== MONIKA 7-DAY MACRO GROUNDING & 5-DAY MACRO NARRATIVE CONTEXT ===\n"
                f"{chronicle_block}"
                f"INSTITUTIONAL MACRO BASELINE:\n{macro_core_block}\n\n"
                f"UPCOMING HIGH-IMPACT ECONOMIC CALENDAR (CONSENSUS BENCHMARKS):\n{cal_block}\n\n"
                f"ESTABLISHED 7-DAY HIGH-IMPACT THEMES & HISTORICAL SHOCKS:\n{themes_block}\n\n"
                f"TEMPORAL GROUNDING RULES FOR THIS BATCH:\n"
                f"1. REHASH / ALREADY KNOWN: If an item merely repeats or comments on an ongoing 7-day theme or known conflict without fresh concrete quantitative data/unprecedented actions, cap at MEDIUM or LOW (tag 'NARRATIVE_EXHAUSTION').\n"
                f"2. IN-LINE DATA: If scheduled data release meets consensus/forecast above, cap at HIGH or MEDIUM (tag 'PRICED_IN', NEVER mark BREAKING).\n"
                f"3. EXTREME DATA SURPRISE: If scheduled data release deviates significantly from the calendar forecast above (surprise_magnitude='large'), classify as BREAKING (tag 'FRESH_CATALYST').\n"
                f"4. UNPRECEDENTED SHOCK: If a news item introduces concrete NEW emergency measures, retaliatory escalations, or unprecedented actions not in chronicles/themes above, classify as BREAKING (tag 'FRESH_CATALYST').\n"
                f"5. DAMPENER / DE-ESCALATION: If a news item eases active market tension (e.g. negotiation progress, tariff exemption, ceasefire), classify whether it acts as a risk relief dampener (tag 'DEESCALATION_RELIEF')."
            )
            self._macro_context_cache = context
            self._macro_context_cache_time = now_utc
            return context
        except Exception as e:
            logger.debug(f"Failed to build 7-day macro grounding context (non-fatal): {e}")
            return "=== 7-DAY MACRO CONTEXT ===\nEvaluate news items objectively based on fresh catalysts vs market consensus."

    async def _build_5day_macro_context(self, session: AsyncSession, now_utc: datetime) -> str:
        """Backwards compatibility alias for _build_7day_macro_grounding_context."""
        return await self._build_7day_macro_grounding_context(session, now_utc)

    async def _get_calendar_impact_priors(
        self, session: AsyncSession, batch: list[NewsItem], now_utc: datetime
    ) -> dict[int, Optional[str]]:
        from sqlalchemy import select

        from monika.infrastructure.database.models import EconomicCalendar

        priors: dict[int, Optional[str]] = {}
        MIN_TOKEN_OVERLAP = 2  # FIX: sebelumnya 1 — terlalu longgar, rawan false-match
        MIN_OVERLAP_RATIO = 0.25  # FIX BARU: overlap harus jadi porsi berarti dari nama event

        for idx, item in enumerate(batch, start=1):
            priors[idx] = None
            if not item.currency_tags:
                continue
            currencies = [c.strip().upper() for c in item.currency_tags.split(",") if c.strip() and c.strip() != "NON"]
            if not currencies:
                continue
            check_time = ensure_utc(item.fetched_at) or now_utc
            candidates = (
                (
                    await session.execute(
                        select(EconomicCalendar)
                        .where(EconomicCalendar.currency.in_(currencies))
                        .where(EconomicCalendar.event_time >= check_time - timedelta(hours=2))
                        .where(EconomicCalendar.event_time <= check_time + timedelta(hours=1))
                    )
                )
                .scalars()
                .all()
            )
            if not candidates:
                continue
            title_tokens = set(w for w in (item.title or "").lower().split() if len(w) > 4)
            best_match, best_overlap, best_ratio = None, 0, 0.0
            for ev in candidates:
                ev_tokens = set(w for w in (ev.event_name or "").lower().split() if len(w) > 4)
                if not ev_tokens:
                    continue
                overlap = len(title_tokens & ev_tokens)
                ratio = overlap / len(ev_tokens)
                if overlap > best_overlap or (overlap == best_overlap and ratio > best_ratio):
                    best_overlap, best_ratio, best_match = overlap, ratio, ev
            if best_match and best_overlap >= MIN_TOKEN_OVERLAP and (best_ratio >= MIN_OVERLAP_RATIO):
                priors[idx] = (best_match.impact or "").lower()
            else:
                # NEW fallback: judul tidak match via token overlap (paraphrase umum, e.g. "US jobs
                # beat forecast" vs event_name "Non-Farm Payrolls"), tapi ada event HIGH currency-sama
                # dalam window WAKTU SANGAT SEMPIT (±20 menit) — itu sangat mungkin event yang sama.
                tight_candidates = [
                    ev
                    for ev in candidates
                    if (ev.impact or "").lower() == "high"
                    and ev.event_time is not None
                    and (ev_dt := ensure_utc(ev.event_time)) is not None
                    and abs((ev_dt - check_time).total_seconds()) <= 1200
                ]
                if tight_candidates:
                    priors[idx] = "high"
        return priors

    def _is_potentially_relevant(self, title: Optional[str], summary: Optional[str]) -> bool:
        text = f"{title or ''} {summary or ''}".lower()

        # 1. Urgent/breaking headlines always relevant (H-3)
        URGENT_TAGS = [
            "breaking",
            "flash",
            "urgent",
            "alert",
            "bulletin",
            "just in",
            "emergency",
            "war",
            "sanction",
            "crisis",
            "attack",
            "explosion",
            "embargo",
            "escalation",
            "coup",
            "default",
            "bailout",
            "ultimatum",
            "threaten",
            "retaliat",
        ]
        if any(tag in text for tag in URGENT_TAGS):
            return True

        from monika.domain.market.news_impact_keywords import GEOPOLITICAL_HOTSPOT_ENTITIES, GEOPOLITICAL_LEADERS

        # 1.1 Geopolitical Hotspot + Leader combination (e.g. Trump + Iran, Putin + Xi)
        has_leader = any(leader in text for leader in GEOPOLITICAL_LEADERS)
        has_hotspot = any(spot in text for spot in GEOPOLITICAL_HOTSPOT_ENTITIES)
        if has_leader and has_hotspot:
            return True

        # 1.2 High-level diplomatic summits, accords, and strategic talks
        if any(w in text for w in ("trilateral", "bilateral", "summit", "diplomatic", "accord")):
            return True

        from monika.infrastructure.database.adapters import CURRENCY_KEYWORDS

        for keywords in CURRENCY_KEYWORDS.values():
            if any(kw in text for kw in keywords):
                return True
        if any(kw in text for kw in HIGH_IMPACT_KEYWORDS) or any(kw in text for kw in SHOCK_KEYWORDS):
            return True

        GENERIC_MACRO_TERMS = [
            "stock market",
            "wall street",
            "bond yield",
            "crude oil",
            "commodities",
            "risk appetite",
            "safe haven",
            "market selloff",
            "rally",
            "volatility",
            "crypto",
            "bitcoin",
            "recession",
            "tariff",
            "inflation",
            "cpi",
            "pce",
            "gdp",
            "nfp",
            "employment",
            "unemployment",
            "fomc",
            "fed",
            "ecb",
            "boe",
            "boj",
            "pboc",
            "snb",
            "rba",
            "rbnz",
            "opec",
            "treasury",
            "equities",
            "gold",
            "dollar",
            "euro",
            "yen",
            "pound",
            "oil",
            "nasdaq",
            "dow",
            "s&p",
            "dxy",
            "vix",
            "rate hike",
            "rate cut",
            "stimulus",
            "debt ceiling",
            "central bank",
            "interest rate",
        ]
        return any(kw in text for kw in GENERIC_MACRO_TERMS)

    async def _get_recent_classified_titles(self, session: AsyncSession, hours: int = 12) -> list[str]:
        from sqlalchemy import select

        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        res = await session.execute(
            select(NewsItem.title).where(NewsItem.fetched_at >= since).where(NewsItem.impact.in_(["BREAKING", "HIGH"]))
        )
        return [r for r in res.scalars() if r]
