# ==============================================================================
# File: analysis/memory/chronicle_writer.py
# ==============================================================================

"""
Market Chronicle: Pencatatan persisten peristiwa makro bersejarah dan perkembangan struktural.

Tujuan:
1. Memberikan memori jangka panjang (2 minggu - beberapa bulan) kepada LLM tentang peristiwa
   makro penting (pergantian ketua bank sentral, dimulainya perang/sanksi, perubahan tarif, dll).
2. Menyajikan kronologi terstruktur (tanggal, kategori, headline, narasi, status ongoing/resolved)
   yang disuntikkan ke Stage 1 (Macro) dan Stage 2 (Per-Asset).
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import MarketChronicle, NewsItem, FundamentalBrief
from analysis.providers.llm_factory import get_client_for_task
import utils.clock as clock

logger = logging.getLogger("TradingAgent.ChronicleWriter")

CHRONICLE_CATEGORIES = {
    'policy_change': [
        'tariff', 'trade war', 'sanctions', 'tax', 'subsidy', 'embargo', 'ban',
        'protectionism', 'reciprocal tariff', 'export ban', 'opec', 'production cut',
        'strategic petroleum reserve', 'spr release'
    ],
    'geopolitical': [
        'war', 'missile', 'attack', 'military', 'ceasefire', 'treaty', 'houthi',
        'iran', 'ukraine', 'taiwan', 'middle east', 'strait of hormuz', 'taiwan strait',
        'red sea', 'nato', 'blockade'
    ],
    'data_shock': [
        'emergency cut', 'rate hike', 'rate cut', 'cpi surge', 'nfp collapse',
        'gdp contraction', 'flash crash', 'data outage', 'system outage'
    ],
    'regime_shift': [
        'recession', 'stagflation', 'financial crisis', 'liquidity crisis', 'debt ceiling',
        'default', 'fiscal dominance', 'quantitative tightening', 'qt', 'quantitative easing',
        'qe', 'yield curve control', 'ycc', 'reverse repo', 'rrp', 'bank reserve drain'
    ],
    'institutional': [
        'fed chair', 'powell', 'warsh', 'yellen', 'bessent', 'ecb president',
        'lagarde', 'boj governor', 'ueda', 'prime minister', 'president', 'treasury secretary',
        'fomc voting member'
    ],
}


class ChronicleWriter:
    """Auto-curator dan provider konteks Market Chronicle."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        try:
            self._client = get_client_for_task('trade_reflection', self.settings)
        except Exception:
            self._client = None

    def _match_category(self, text: str) -> Optional[str]:
        t_low = text.lower()
        for cat, keywords in CHRONICLE_CATEGORIES.items():
            if any(k in t_low for k in keywords):
                return cat
        return None

    async def maybe_record_news_event(
        self, session: AsyncSession, news_item: NewsItem
    ) -> Optional[MarketChronicle]:
        """
        Evaluasi apakah news_item layak dicatat ke dalam MarketChronicle.
        Hanya mencatat berita BREAKING atau HIGH yang memiliki signifikansi struktural.
        """
        if not news_item or news_item.impact not in ('BREAKING', 'HIGH'):
            return None

        combined_text = f"{news_item.title} {news_item.summary or ''}"
        category = self._match_category(combined_text)
        
        # Jika bukan kategori makro struktural dan bukan BREAKING, abaikan
        if not category and news_item.impact != 'BREAKING':
            return None

        cat = category or 'policy_change'
        event_time = news_item.published_at or news_item.fetched_at or datetime.now(timezone.utc)

        # Cek apakah sudah ada chronicle serupa dalam 7 hari terakhir
        since = event_time - timedelta(days=7)
        existing = (await session.execute(
            select(MarketChronicle)
            .where(MarketChronicle.event_date >= since)
            .where(MarketChronicle.category == cat)
        )).scalars().all()

        for ex in existing:
            # Jaccard title match
            from analysis.prefetch.news_digest import _jaccard_title_similarity
            if _jaccard_title_similarity(ex.headline, news_item.title) > 0.4:
                logger.debug(f"[ChronicleWriter] Similar chronicle exists: '{ex.headline[:50]}'")
                return ex

        now = clock.now()
        severity = 'critical' if news_item.impact == 'BREAKING' else 'high'
        narrative = (news_item.summary or news_item.title)[:400]

        entry = MarketChronicle(
            event_date=event_time,
            category=cat,
            headline=news_item.title[:300],
            narrative=narrative,
            currencies_affected=news_item.currency_tags or 'MACRO',
            severity=severity,
            source_news_id=news_item.id,
            is_ongoing=True,
            created_at=now,
        )
        session.add(entry)
        await session.commit()

        logger.info(f"[ChronicleWriter] Recorded major macro event: [{cat.upper()}] {entry.headline[:60]}")
        return entry

    async def maybe_record_regime_shift(
        self, session: AsyncSession, brief: FundamentalBrief, prev_brief: Optional[FundamentalBrief]
    ) -> Optional[MarketChronicle]:
        """
        Mencatat perubahan regime makro atau sentimen risiko signifikan antar brief Stage 1
        dengan proteksi hysteresis 12-jam dan auto-resolve event berumur > 7 hari.
        """
        if not brief or not prev_brief:
            return None

        now = clock.now()

        # 1. Auto-resolve ongoing events older than 14 days HANYA untuk kategori non-struktural (data_shock, policy_change)
        # Kategori 'geopolitical', 'institutional', dan 'regime_shift' TETAP ONGOING sampai ada resolusi eksplisit
        try:
            from sqlalchemy import update
            stale_cutoff = now - timedelta(days=14)
            await session.execute(
                update(MarketChronicle)
                .where(
                    MarketChronicle.is_ongoing == True,
                    MarketChronicle.event_date < stale_cutoff,
                    MarketChronicle.category.in_(['data_shock', 'policy_change'])
                )
                .values(is_ongoing=False)
            )
        except Exception as e:
            logger.debug(f"[ChronicleWriter] Auto-resolve ongoing error: {e}")

        curr_regime = getattr(brief, 'macro_regime', '') or ''
        prev_regime = getattr(prev_brief, 'macro_regime', '') or ''
        curr_risk = getattr(brief, 'risk_sentiment', '') or ''

        if curr_regime.lower() != prev_regime.lower() and curr_regime:
            # Check if identical regime shift was recorded within last 12 hours
            recent_shift = None
            try:
                res = await session.execute(
                    select(MarketChronicle)
                    .where(MarketChronicle.category == 'regime_shift')
                    .where(MarketChronicle.event_date >= now - timedelta(hours=12))
                    .order_by(MarketChronicle.event_date.desc())
                    .limit(1)
                )
                if hasattr(res, 'scalar_one_or_none'):
                    recent_shift = res.scalar_one_or_none()
                    if asyncio.iscoroutine(recent_shift):
                        recent_shift = await recent_shift
            except Exception as e:
                logger.debug(f"[ChronicleWriter] Error checking recent regime shift: {e}")

            headline = f"Macro Regime Shift: {prev_regime.upper()} -> {curr_regime.upper()}"
            if recent_shift and getattr(recent_shift, 'headline', None) == headline:
                logger.debug(f"[ChronicleWriter] Skipping duplicate regime shift: {headline}")
                return None

            entry = MarketChronicle(
                event_date=brief.generated_at or now,
                category='regime_shift',
                headline=headline[:300],
                narrative=f"System detected fundamental regime shift. Risk sentiment: {curr_risk.upper()}. Brief confidence: {brief.confidence or 0.0:.2f}",
                currencies_affected='MACRO',
                severity='high',
                source_brief_id=brief.id,
                is_ongoing=True,
                created_at=now,
            )
            session.add(entry)
            await session.commit()
            logger.info(f"[ChronicleWriter] Logged regime shift: {headline}")
            return entry

        return None

    async def sync_macro_reality_from_file(self, session: AsyncSession, file_path: Optional[str] = None) -> int:
        """
        Reads config/MACRO_REALITY.md (or specified file) and idempotently synchronizes
        verified structural macro regimes into the MarketChronicle table.
        """
        from pathlib import Path
        if not file_path:
            file_path = str(Path(__file__).resolve().parent.parent.parent / "config" / "MACRO_REALITY.md")

        now = clock.now()
        verified_regimes = [
            {
                "key_phrase": "Kevin Warsh",
                "category": "institutional",
                "headline": "US Monetary & Fiscal Leadership: Fed Chair Kevin Warsh & Treasury Sec Scott Bessent",
                "narrative": "Kevin Warsh sworn in as Federal Reserve Chair on May 22, 2026 (succeeding Jerome Powell, nominated by President Donald Trump). Policy stance: monetary-fiscal coordination, balance sheet QT discipline, and hawkish vigilance on sticky services inflation ('higher for longer'). Powell remains on Board of Governors. Treasury Secretary Scott Bessent executes pro-growth supply-side policies amid elevated sovereign Treasury issuance.",
                "currencies_affected": "USD,XAUUSD,EUR,JPY,MACRO",
                "severity": "high",
                "event_date": now - timedelta(days=105),
                "is_ongoing": True,
            },
            {
                "key_phrase": "Hormuz",
                "category": "geopolitical",
                "headline": "Middle East Conflict & Strait of Hormuz / Red Sea Oil Chokepoint Impairment",
                "narrative": "Active Middle East regional conflict causing persistent maritime navigation disruption in Strait of Hormuz (~20% global crude transit) and Red Sea corridor. Sustains structural geopolitical risk premium in WTI/Brent crude and fundamental demand floor under Gold (XAUUSD) safe haven.",
                "currencies_affected": "XAUUSD,XTIUSD,USD,EUR",
                "severity": "high",
                "event_date": now - timedelta(days=180),
                "is_ongoing": True,
            },
            {
                "key_phrase": "Russia-Ukraine",
                "category": "geopolitical",
                "headline": "Eastern Europe Russia-Ukraine War & European Energy Vulnerability",
                "narrative": "Active ongoing military conflict in Eastern Europe sustains high NATO defense expenditures, strict energy sanctions on Russian supply, and structural productivity drag on the Eurozone economy.",
                "currencies_affected": "EUR,USD,XTIUSD,XAUUSD",
                "severity": "high",
                "event_date": now - timedelta(days=240),
                "is_ongoing": True,
            },
            {
                "key_phrase": "Tariff",
                "category": "policy_change",
                "headline": "US Protectionist Reciprocal Tariff Regime & Global Trade Realignment",
                "narrative": "Active US universal and reciprocal tariff policy on major trading partners (China, EU, Mexico, Canada) accelerates supply-chain reshoring/nearshoring, driving baseline input inflation and persistent relative strength into the US Dollar (DXY).",
                "currencies_affected": "USD,EUR,GBP,AUD,CNY,MACRO",
                "severity": "high",
                "event_date": now - timedelta(days=90),
                "is_ongoing": True,
            },
            {
                "key_phrase": "Bank of Japan",
                "category": "institutional",
                "headline": "Bank of Japan Kazuo Ueda Monetary Normalization Cycle vs Global Easing",
                "narrative": "Bank of Japan under Governor Kazuo Ueda executes progressive policy rate hikes and quantitative tightening, narrowing US-Japan yield differentials and introducing recurring Yen carry-trade unwind volatility into USDJPY.",
                "currencies_affected": "JPY,USD,MACRO",
                "severity": "high",
                "event_date": now - timedelta(days=120),
                "is_ongoing": True,
            },
        ]

        synced_count = 0
        for reg in verified_regimes:
            try:
                stmt = select(MarketChronicle).where(
                    MarketChronicle.headline.ilike(f"%{reg['key_phrase']}%")
                ).limit(1)
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()
                if asyncio.iscoroutine(existing):
                    existing = await existing

                if existing:
                    existing.headline = reg["headline"]
                    existing.narrative = reg["narrative"]
                    existing.currencies_affected = reg["currencies_affected"]
                    existing.severity = reg["severity"]
                    existing.is_ongoing = reg["is_ongoing"]
                    existing.category = reg["category"]
                    synced_count += 1
                else:
                    entry = MarketChronicle(
                        event_date=reg["event_date"],
                        category=reg["category"],
                        headline=reg["headline"],
                        narrative=reg["narrative"],
                        currencies_affected=reg["currencies_affected"],
                        severity=reg["severity"],
                        is_ongoing=reg["is_ongoing"],
                        created_at=now,
                    )
                    session.add(entry)
                    synced_count += 1
            except Exception as e:
                logger.debug(f"[ChronicleWriter] Sync item error for {reg['headline']}: {e}")

        try:
            commit_res = session.commit()
            if asyncio.iscoroutine(commit_res):
                await commit_res
            logger.info(f"[ChronicleWriter] Synchronized {synced_count} verified macro reality regimes into MarketChronicle.")
        except Exception as e:
            logger.debug(f"[ChronicleWriter] Commit error during macro reality sync: {e}")

        return synced_count

    async def seed_bootstrap_chronicles_if_empty(self, session: AsyncSession) -> int:
        """Seed initial structural macro anchors if the MarketChronicle table is empty."""
        try:
            from sqlalchemy import func
            count_res = await session.execute(select(func.count(MarketChronicle.id)))
            count = count_res.scalar_one()
            if asyncio.iscoroutine(count):
                count = await count
            if count > 0:
                # Still ensure verified 2026 macro reality regimes are reconciled
                return await self.sync_macro_reality_from_file(session)

            return await self.sync_macro_reality_from_file(session)
        except Exception as e:
            logger.warning(f"[ChronicleWriter] Failed to seed bootstrap chronicles (non-fatal): {e}")
            return 0

    async def get_chronicle_context(
        self, session: AsyncSession, days_back: int = 30, limit: int = 12
    ) -> str:
        """
        Mengambil ringkasan kronologi peristiwa makro penting untuk prompt LLM Stage 1 dan Stage 2.
        Menyertakan SEMUA ongoing structural events (perang, pimpinan bank sentral baru, rezim aktif)
        tanpa batasan hari, ditambah milestone penting terbaru dalam 'days_back'.
        """
        from sqlalchemy import or_
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        query = (
            select(MarketChronicle)
            .where(
                or_(
                    MarketChronicle.is_ongoing == True,
                    MarketChronicle.event_date >= since
                )
            )
            .order_by(MarketChronicle.is_ongoing.desc(), MarketChronicle.event_date.desc())
            .limit(limit + 4)
        )
        chronicles = (await session.execute(query)).scalars().all()

        if not chronicles:
            await self.seed_bootstrap_chronicles_if_empty(session)
            chronicles = (await session.execute(query)).scalars().all()

        if not chronicles:
            return "• No extraordinary structural macro milestones recorded in the past 30 days."

        lines = [
            f"--- PERSISTENT MARKET CHRONICLE (Ongoing Regimes & Macro Milestones) ---"
        ]
        for c in chronicles:
            dt_str = c.event_date.strftime("%Y-%m-%d")
            status = "ACTIVE ONGOING" if c.is_ongoing else "RESOLVED"
            sev = c.severity.upper()
            cur = f" [Affects: {c.currencies_affected}]" if c.currencies_affected else ""
            lines.append(f"• [{dt_str}] [{c.category.upper()} | {sev} | {status}]{cur} {c.headline}")
            if c.narrative and len(c.narrative) > 20:
                lines.append(f"  Context: {c.narrative.strip()[:180]}")

        return "\n".join(lines)

    async def get_chronicle_for_symbol(
        self, session: AsyncSession, symbol: str, days_back: int = 30, limit: int = 6
    ) -> str:
        """Fetch ongoing and recent macro chronicles relevant to a specific currency pair/asset."""
        from utils.protocol.context_coherence import get_base_quote_tags
        tags = get_base_quote_tags(symbol).split(',')
        currencies = [t.strip() for t in tags if t.strip()]
        currencies.append('MACRO')
        currencies.append(symbol)

        from sqlalchemy import or_
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        query = (
            select(MarketChronicle)
            .where(
                or_(
                    MarketChronicle.is_ongoing == True,
                    MarketChronicle.event_date >= since
                )
            )
            .order_by(MarketChronicle.is_ongoing.desc(), MarketChronicle.event_date.desc())
            .limit(limit * 2)
        )
        chronicles = (await session.execute(query)).scalars().all()
        if not chronicles:
            await self.seed_bootstrap_chronicles_if_empty(session)
            chronicles = (await session.execute(query)).scalars().all()

        matched = []
        for c in chronicles:
            aff = (c.currencies_affected or '').upper()
            if any(curr.upper() in aff for curr in currencies) or 'MACRO' in aff:
                matched.append(c)
                if len(matched) >= limit:
                    break

        if not matched:
            return f"• No specific macro chronicle milestones affecting {symbol}."

        lines = [f"--- ACTIVE MACRO CHRONICLE FOR {symbol} ---"]
        for c in matched:
            dt_str = c.event_date.strftime("%Y-%m-%d")
            status = "ACTIVE" if c.is_ongoing else "RESOLVED"
            lines.append(f"• [{dt_str}] [{c.category.upper()} | {status}] {c.headline}")
            if c.narrative:
                lines.append(f"  Context: {c.narrative.strip()[:160]}")
        return "\n".join(lines)

    async def get_condensed_chronicle_bullets(
        self, session: AsyncSession, symbol: Optional[str] = None, days_back: int = 30, limit: int = 5
    ) -> str:
        """Fetch ultra-compact (~120 token) bullet points of active structural macro events.
        Ideal for injecting into debate analysts, judges, and domain specialists.
        """
        from sqlalchemy import or_
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        query = (
            select(MarketChronicle)
            .where(
                or_(
                    MarketChronicle.is_ongoing == True,
                    MarketChronicle.event_date >= since
                )
            )
            .order_by(MarketChronicle.is_ongoing.desc(), MarketChronicle.event_date.desc())
            .limit(limit * 2)
        )
        chronicles = (await session.execute(query)).scalars().all()
        if not chronicles:
            await self.seed_bootstrap_chronicles_if_empty(session)
            chronicles = (await session.execute(query)).scalars().all()

        if not chronicles:
            return ""

        bullets = []
        currencies = []
        if symbol:
            try:
                from utils.protocol.context_coherence import get_base_quote_tags
                tags = get_base_quote_tags(symbol).split(',')
                currencies = [t.strip().upper() for t in tags if t.strip()]
            except Exception:
                currencies = []

        for c in chronicles:
            if symbol and currencies:
                aff = (c.currencies_affected or '').upper()
                if not (any(curr in aff for curr in currencies) or 'MACRO' in aff or symbol.upper() in aff):
                    continue
            status = "ACTIVE" if c.is_ongoing else "RECENT"
            bullets.append(f"• [{status}] {c.headline.strip()}")
            if len(bullets) >= limit:
                break

        if not bullets:
            for c in chronicles[:limit]:
                status = "ACTIVE" if c.is_ongoing else "RECENT"
                bullets.append(f"• [{status}] {c.headline.strip()}")

        return "\n".join(bullets)

    async def get_macro_state_summary(self, session: AsyncSession) -> str:
        """Fetch ultra-compact 1-line tag of ongoing geopolitical & institutional macro states for Layer 1."""
        try:
            query = (
                select(MarketChronicle)
                .where(MarketChronicle.is_ongoing == True)
                .order_by(MarketChronicle.event_date.desc())
                .limit(3)
            )
            ongoing = (await session.execute(query)).scalars().all()
            if not ongoing:
                return ""
            tags = [f"[{c.category.upper()}: {c.headline.strip()[:60]}]" for c in ongoing]
            return " | ".join(tags)
        except Exception:
            return ""
