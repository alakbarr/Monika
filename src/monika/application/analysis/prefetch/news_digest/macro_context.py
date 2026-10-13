# ==============================================================================
# File: application/analysis/prefetch/news_digest/macro_context.py
# ==============================================================================

"""
Macro context builder, calendar priors, and pre-filtering relevance checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

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


class MacroContextMixin(_NewsDigestMixinBase):
    """Mixin providing 5-day macro context, calendar impact priors, and headline relevance."""

    def invalidate_macro_context_cache(self) -> None:
        """Explicitly invalidate in-memory 5-day macro context cache."""
        self._macro_context_cache = None
        self._macro_context_cache_time = None
        self._last_known_brief_id = None
        self._last_known_breaking_id = None

    async def _build_5day_macro_context(self, session: AsyncSession, now_utc: datetime) -> str:
        """
        Membangun ringkasan narasi makro dan tema-tema berita signifikan dari 5 hari terakhir (120 jam)
        dengan arsitektur Hybrid Event-Driven Caching (TTL default 60 menit + Reactive Invalidation saat
        terdapat FundamentalBrief baru atau berita BREAKING baru).
        """
        from sqlalchemy import func, select

        from monika.infrastructure.database.models import FundamentalBrief, NewsItem

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
            # 1. Ambil brief fundamental terbaru untuk baseline regime & bias
            brief = (
                await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
            ).scalar_one_or_none()

            macro_summary = "Regime: BALANCED | Risk: NEUTRAL | Biases: Mixed"
            if brief:
                regime = getattr(brief, "macro_regime", "mixed")
                risk = getattr(brief, "risk_sentiment", "mixed")
                cb = getattr(brief, "currency_bias", {}) or {}
                if isinstance(cb, dict) and cb:
                    bias_str = ", ".join([f"{k}:{v}" for k, v in cb.items() if v != "neutral"][:6])
                else:
                    bias_str = "Balanced"
                macro_summary = f"Regime: {str(regime).upper()} | Risk: {str(risk).upper()} | Biases: {bias_str}"

            try:
                from monika.application.analysis.memory.chronicle_writer import ChronicleWriter

                c_writer = ChronicleWriter(self.settings)
                c_bullets = await c_writer.get_condensed_chronicle_bullets(session, limit=4)
                if c_bullets:
                    macro_summary += f"\nActive Structural Chronicles:\n{c_bullets}"
            except Exception:
                pass

            # 2. Ambil berita HIGH/BREAKING dari 5 hari terakhir (120 jam)
            five_days_ago = now_utc - timedelta(days=5)
            recent_high_items = (
                await session.execute(
                    select(NewsItem.title, NewsItem.currency_tags, NewsItem.impact, NewsItem.fetched_at)
                    .where(NewsItem.fetched_at >= five_days_ago)
                    .where(NewsItem.impact.in_(["BREAKING", "HIGH"]))
                    .order_by(NewsItem.fetched_at.desc())
                    .limit(30)
                )
            ).all()

            theme_lines = []
            seen_titles = []
            for row in recent_high_items:
                t = row[0]
                if not t:
                    continue
                # Filter similar titles to keep the theme list compact and high-signal
                if any(_jaccard_title_similarity(t, st) > 0.45 for st in seen_titles):
                    continue
                seen_titles.append(t)
                cur = row[1] or "MACRO"
                imp = row[2]
                r_utc = ensure_utc(row[3]) if row[3] else None
                age_days = max(0, round((now_utc - r_utc).total_seconds() / 86400, 1)) if r_utc else 0
                theme_lines.append(f"• [{cur}] ({imp}, {age_days}d ago): {t[:110]}")
                if len(theme_lines) >= 8:
                    break

            themes_block = (
                "\n".join(theme_lines) if theme_lines else "• No dominant multi-day shock recorded in recent 5 days."
            )

            # SOTA Memory Grounding: Inject active structural chronicles (ongoing wars, central bank leadership, tariffs)
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
                f"--- 5-DAY MACRO NARRATIVE & MARKET THEMES CONTEXT ---\n"
                f"{chronicle_block}"
                f"PREVAILING BASELINE: {macro_summary}\n"
                f"ESTABLISHED 5-DAY HIGH-IMPACT THEMES & CATALYSTS:\n"
                f"{themes_block}\n\n"
                f"TEMPORAL EVALUATION INSTRUCTIONS FOR THIS BATCH:\n"
                f"1. NARRATIVE EXHAUSTION / REHASH: If a news item merely repeats or provides speculative commentary on an already established theme above without new quantitative data, formal actions, or fresh dates, cap at MEDIUM or LOW (tag with 'NARRATIVE_EXHAUSTION').\n"
                f"2. FRESH CATALYST / SHOCK: If a news item introduces concrete NEW measures, retaliatory escalations, or unexpected deviations from the established baseline above, classify as HIGH or BREAKING (tag with 'FRESH_CATALYST').\n"
                f"3. DAMPENER / DE-ESCALATION: If a news item eases active market tension (e.g. negotiation progress, tariff exemption, diplomatic pause, ceasefire), classify whether it acts as a risk relief dampener (tag with 'DEESCALATION_RELIEF')."
            )
            self._macro_context_cache = context
            self._macro_context_cache_time = now_utc
            return context
        except Exception as e:
            logger.debug(f"Failed to build 5-day macro context (non-fatal): {e}")
            return "--- 5-DAY MACRO CONTEXT ---\nEvaluate news items objectively based on fresh catalysts vs market consensus."

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
