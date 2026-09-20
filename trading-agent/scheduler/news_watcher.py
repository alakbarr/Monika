# ==============================================================================
# File: scheduler/news_watcher.py
# ==============================================================================

"""
News Watcher: Filter breaking news berbasis kata kunci (minim biaya API).

Fungsi:
1. Memantau berita masuk setiap N menit.
2. Filter awal dengan regex (gratis) sebelum opsi klasifikasi LLM.
3. Memicu re-analisis (Stage 1 & 2) secara selektif jika ada berita berdampak tinggi (High Impact).
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_session
from database.models import NewsItem, ActivityLog

logger = logging.getLogger("TradingAgent.NewsWatcher")


# =============================================================================
# Keyword Configuration
# =============================================================================

from utils.market.news_impact_keywords import HIGH_IMPACT_KEYWORDS, SHOCK_KEYWORDS


# Kata kunci Medium-Impact — dipantau tapi tidak memicu re-analisis instan
MEDIUM_IMPACT_KEYWORDS = [
    "inflation", "cpi", "pce", "jobs report", "trade deficit",
    "gdp", "retail sales", "pmi", "ism", "housing",
    "fed minutes", "fomc minutes", "fed speak", "hawkish", "dovish",
    "yield curve", "treasury", "bond selloff", "risk appetite",
    "geopolitical tension", "oil price", "gold price",
    "ecb", "bank of england", "reserve bank", "central bank",
]

# Pemetaan tag mata uang untuk targeted re-analysis aset
CURRENCY_TO_SYMBOLS: dict[str, list[str]] = {
    "USD": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "XTIUSD", "XBRUSD"],
    "EUR": ["EURUSD"],
    "GBP": ["GBPUSD"],
    "JPY": ["USDJPY"],
    "AUD": ["AUDUSD"],
    "XAU": ["XAUUSD"],
    "GOLD": ["XAUUSD"],
    "OIL": ["XTIUSD", "XBRUSD"],
    "XTI": ["XTIUSD", "XBRUSD"],
    "XBR": ["XBRUSD", "XTIUSD"],
    "BTC": ["BTCUSD"],
    "CRYPTO": ["BTCUSD"],
}


class NewsWatcher:
    """
    Pemantau `news_items` untuk mendeteksi breaking news dan memicu re-analisis.

    Penggunaan:
        watcher = NewsWatcher(settings, cycle_scheduler)
        await watcher.start()
    """

    def __init__(self, settings: dict, cycle_scheduler=None, fundamental_stage=None, per_asset_stage=None, position_guardian=None, execution_service=None):
        """
        Args:
            settings:           Full settings dict.
            cycle_scheduler:    CycleScheduler — for full cycle re-runs.
            fundamental_stage:  FundamentalStage — for Stage 1 only re-runs.
            per_asset_stage:    PerAssetStage — for targeted per-symbol re-runs.
            position_guardian:  PositionGuardian — for protective emergency actions.
            execution_service:  ExecutionService — for executing trade proposals.
        """
        self.settings = settings
        sched_cfg = settings.get("trading", {}).get("schedule", {})
        self.check_interval_minutes: float = sched_cfg.get("news_check_minutes", 5)

        self._cycle_scheduler    = cycle_scheduler
        self._fundamental_stage  = fundamental_stage
        self._per_asset_stage    = per_asset_stage
        self._position_guardian  = position_guardian
        self._execution_service  = execution_service
        self._post_release_analyzer: Optional[Any] = None
        self._activity_log: Optional[Any] = None

        self._last_seen_at: Optional[datetime] = None
        self._running = False
        self._stop_event = asyncio.Event()

        # Throttling klasifikasi LLM: batasi agar tidak cepat habis kuota API
        self._classify_tick_counter: int = 0
        self._classify_every_n_ticks: int = 3   # ~15 min when check_interval=5
        self._classify_min_items: int = 3        # don't burn a call for 1-2 items

        # Circuit breaker: membatasi maksimal analisis ulang (full-cycle) dalam sehari
        self._forced_reruns_today: int = 0
        self._forced_rerun_day: Optional[str] = None  # YYYY-MM-DD UTC
        self._max_forced_reruns: int = int(
            settings.get("trading", {}).get("schedule", {}).get("max_news_reruns_per_day", 3)
        )
        self._background_tasks: set[asyncio.Task] = set()
        self._run_lock = asyncio.Lock()
        self._targeted_reruns_today: int = 0
        self._max_targeted_reruns: int = int(
            settings.get("news_classification_control", {}).get("max_targeted_reruns_per_day", 10)
        )

        # Pre-compile regex untuk performa yang optimal
        high_pattern = "|".join(re.escape(k) for k in HIGH_IMPACT_KEYWORDS)
        medium_pattern = "|".join(re.escape(k) for k in MEDIUM_IMPACT_KEYWORDS)
        shock_pattern = "|".join(re.escape(k) for k in SHOCK_KEYWORDS)
        self._high_re   = re.compile(high_pattern, re.IGNORECASE)
        self._medium_re = re.compile(medium_pattern, re.IGNORECASE)
        self._shock_re  = re.compile(shock_pattern, re.IGNORECASE)

        # Track last reanalysis time per symbol to prevent spam
        self._last_reanalysis: dict[str, datetime] = {}
        self._min_reanalysis_interval_minutes: int = 45  # min 45 min between reruns per symbol
        
        # FIX-4: Persistent state file untuk survive restart
        self._state_file: str = settings.get(
            'trading', {}).get('schedule', {}).get(
            'news_watcher_state_file',
            'data/news_watcher_state.json'
        )
        self._load_persistent_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _load_persistent_state(self) -> None:
        """FIX-4: Load persisted state from disk on startup."""
        import json, os
        try:
            if os.path.exists(self._state_file):
                with open(self._state_file, 'r') as f:
                    data = json.load(f)
                ts_str = data.get('last_seen_at')
                if ts_str:
                    self._last_seen_at = datetime.fromisoformat(ts_str)
                reruns = data.get('forced_reruns_today', 0)
                targeted_reruns = data.get('targeted_reruns_today', 0)
                day = data.get('forced_rerun_day')
                today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                if day == today:
                    self._forced_reruns_today = reruns
                    self._targeted_reruns_today = targeted_reruns
                    self._forced_rerun_day = day
                logger.info(f'NewsWatcher: Loaded persistent state. last_seen_at={self._last_seen_at}')
        except Exception as e:
            logger.warning(f'NewsWatcher: Could not load persistent state: {e}')

    def _save_persistent_state(self) -> None:
        """FIX-4: Save state to disk after each run_once."""
        import json, os
        try:
            os.makedirs(os.path.dirname(self._state_file) or '.', exist_ok=True)
            data = {
                'last_seen_at': self._last_seen_at.isoformat() if self._last_seen_at else None,
                'forced_reruns_today': self._forced_reruns_today,
                'targeted_reruns_today': getattr(self, '_targeted_reruns_today', 0),
                'forced_rerun_day': self._forced_rerun_day,
            }
            with open(self._state_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f'NewsWatcher: Could not save persistent state: {e}')

    async def run_once(self) -> dict:
        """
        Mengecek berita terbaru, klasifikasi dampaknya, dan memicu re-analisis bila High Impact.

        Returns:
            Dict status pengecekan (jumlah berita, status trigger).
        """
        if self._run_lock.locked():
            logger.debug("NewsWatcher: run_once already in progress, skipping concurrent pass")
            return {
                "new_items": 0,
                "high_impact_found": 0,
                "medium_impact_found": 0,
                "reanalysis_triggered": False,
                "affected_symbols": [],
                "status": "skipped",
                "reason": "already_running",
            }
        async with self._run_lock:
            return await self._run_once_internal()

    async def _run_once_internal(self) -> dict:
        if self._position_guardian:
            try:
                await self._position_guardian.check_and_protect()
            except Exception as e:
                logger.error(f"PositionGuardian error: {e}")

        async with get_session() as session:
            new_items = await self._fetch_new_news(session)

        if not new_items:
            logger.debug("NewsWatcher: no new items since last check")
            return {
                "new_items": 0,
                "high_impact_found": 0,
                "medium_impact_found": 0,
                "reanalysis_triggered": False,
                "affected_symbols": [],
            }

        logger.info(f"NewsWatcher: {len(new_items)} new news items")

        # Coba menggunakan klasifikasi LLM jika sudah saatnya
        high_items = []
        medium_items = []
        
        try:
            from analysis.prefetch.news_digest import NewsDigestProcessor
            
            # P3-5: Always classify immediately if any item matches shock keywords,
            # bypassing the tick counter/batch size throttle.
            shock_checks = await asyncio.gather(*[self._is_shock_only_strict(n) for n in new_items])
            force_classify = any(shock_checks)
            
            if force_classify or (self._classify_tick_counter % self._classify_every_n_ticks == 0 and len(new_items) >= 1):
                # Quick batch classification via AI / LLM classifier
                processor = NewsDigestProcessor(self.settings)
                async with get_session() as session:
                    await processor.classify_unscored_news(session, hours_back=1)
            
            # Re-query dengan impact filter
            async with get_session() as session:
                urls = [n.url for n in new_items]
                from sqlalchemy import select
                classified = (await session.execute(
                    select(NewsItem)
                    .where(NewsItem.url.in_(urls))
                )).scalars().all()
                
                # FIX: HIGH impact juga trigger re-analisis
                high_items = [n for n in classified if n.impact in ("BREAKING", "HIGH")]
                medium_items = [n for n in classified if n.impact == "MEDIUM"]
        
        except Exception as e:
            logger.error(f'LLM classification pipeline failed — applying conservative SHOCK-only fallback (no full validation layer available): {e}')
            try:
                from utils.infra.notifier import AgentNotifier
                asyncio.create_task(AgentNotifier().send_warning(
                    f'⚠️ News classification pipeline error. Menggunakan fallback shock-keyword konservatif '
                    f'(tanpa validasi berlapis normal) sampai pipeline pulih.\n{str(e)[:150]}'
                ))
            except Exception:
                pass
            # SENGAJA hanya pakai SHOCK_KEYWORDS (bukan HIGH_IMPACT_KEYWORDS penuh yang berisi
            # istilah lunak seperti "recession"/"financial crisis") — regex tanpa validasi
            # berlapis (calendar prior, magnitude cross-check, dedup) jauh lebih rawan false
            # positive, dan false positive di jalur ini langsung memicu forced full-cycle rerun.
            high_items = [n for n in new_items if getattr(n, "impact", None) in ("BREAKING", "HIGH") or await self._is_shock_only_strict(n)]
            medium_items = [n for n in new_items if n not in high_items and self._is_medium_impact(n)]
            fallback_mode = True
        else:
            fallback_mode = False

        self._classify_tick_counter += 1

        result = {
            "new_items": len(new_items),
            "high_impact_found": len(high_items),
            "medium_impact_found": len(medium_items),
            "reanalysis_triggered": False,
            "affected_symbols": [],
        }

        # Narrative Exhaustion Filter: If breaking candidate is tagged NARRATIVE_EXHAUSTION without FRESH_CATALYST,
        # it is an old story repeating; do not trigger an emergency cycle interruption.
        actionable_high_items = []
        for n in high_items:
            sentiments_str = n.sentiment or ''
            if 'NARRATIVE_EXHAUSTION' in sentiments_str and 'FRESH_CATALYST' not in sentiments_str:
                logger.info(f"NewsWatcher: Suppressing emergency rerun for '{n.title[:60]}' (tagged NARRATIVE_EXHAUSTION).")
            else:
                actionable_high_items.append(n)

        if actionable_high_items:
            # When actionable breaking news occurs, invalidate macro context cache reactively
            try:
                from analysis.prefetch.news_digest import NewsDigestProcessor
                NewsDigestProcessor(self.settings).invalidate_macro_context_cache()
                from analysis.prefetch.macro_preprocessor import clear_cache as clear_macro_cache
                clear_macro_cache()
            except Exception:
                pass

            logger.warning(
                f"BREAKING NEWS DETECTED ({len(actionable_high_items)} items): "
                + " | ".join(n.title[:60] for n in actionable_high_items[:3])
            )
            affected = self._get_affected_symbols(actionable_high_items)
            result["affected_symbols"] = affected
            result["reanalysis_triggered"] = True

            async with get_session() as session:
                await self._log(
                    session,
                    f"Breaking news detected: {len(actionable_high_items)} high-impact items — "
                    f"affected: {affected} | top: {actionable_high_items[0].title[:80]}",
                    category="analysis",
                )
                try:
                    from database.event_store import TradingEventStore
                    await TradingEventStore.emit(
                        session=session,
                        event_type="trigger.news_shock",
                        payload={
                            "affected_symbols": affected,
                            "items_count": len(actionable_high_items),
                            "top_title": actionable_high_items[0].title[:100] if actionable_high_items else "",
                        },
                        correlation_id=f"news_{int(datetime.now(timezone.utc).timestamp())}",
                        actor="news_watcher",
                    )
                except Exception:
                    pass

            t = asyncio.create_task(self._trigger_reanalysis(actionable_high_items, affected, fallback_mode=fallback_mode))
            self._background_tasks.add(t)
            t.add_done_callback(self._background_tasks.discard)

        elif medium_items:
            logger.info(
                f"Medium-impact news: {len(medium_items)} items — "
                + medium_items[0].title[:60]
            )
            # Medium impact: log but don't trigger re-analysis immediately
            # (will be picked up by next 6h cycle)
            async with get_session() as session:
                await self._log(
                    session,
                    f"Medium-impact news: {len(medium_items)} items — {medium_items[0].title[:80]}",
                )

        # Update last seen timestamp
        if new_items:
            self._last_seen_at = max(
                n.fetched_at for n in new_items
                if n.fetched_at is not None
            )

        # FIX-4: Persist state after each check
        self._save_persistent_state()

        return result

    async def start(self) -> None:
        """Memulai loop pemantauan (continuous)."""
        self._running = True
        logger.info(f"NewsWatcher starting (interval: {self.check_interval_minutes}m)")

        # FIX-4: Use persisted timestamp if available, else fall back to now - interval
        if self._last_seen_at is None:
            self._last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=self.check_interval_minutes)

        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"NewsWatcher error: {e}")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.check_interval_minutes * 60)
                break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    # Backwards compatibility alias
    watch_once = run_once

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        logger.info("NewsWatcher stop requested.")

    # ------------------------------------------------------------------
    # News fetching
    # ------------------------------------------------------------------

    async def _fetch_new_news(self, session: AsyncSession) -> list[NewsItem]:
        """Mengambil berita baru sejak pengecekan terakhir (berdasarkan _last_seen_at)."""
        since = self._last_seen_at
        if since is None:
            # First run: only look at last N minutes
            since = datetime.now(timezone.utc) - timedelta(minutes=self.check_interval_minutes)

        result = await session.execute(
            select(NewsItem)
            .where(NewsItem.fetched_at > since)
            .order_by(NewsItem.fetched_at.asc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Keyword classification (pure rule-based, no AI)
    # ------------------------------------------------------------------

    def _text_for_classification(self, news: NewsItem) -> str:
        """Menggabungkan title dan summary untuk pencocokan regex."""
        parts = [news.title or ""]
        if news.summary:
            parts.append(news.summary)
        return " ".join(parts)

    def _is_high_impact(self, news: NewsItem) -> bool:
        """Mengembalikan True jika berita cocok dengan kata kunci High Impact."""
        text = self._text_for_classification(news)
        return bool(self._high_re.search(text))

    def _is_shock_only(self, news: NewsItem) -> bool:
        text = self._text_for_classification(news)
        return bool(self._shock_re.search(text))

    async def _matches_recent_calendar_window(self, news: NewsItem) -> bool:
        """Cek apakah berita ini berdekatan (+/-2h) dengan event kalender high-impact."""
        try:
            from database.db import get_session
            from database.models import EconomicCalendar
            from sqlalchemy import select
            check_time = news.fetched_at or datetime.now(timezone.utc)
            async with get_session() as session:
                row = (await session.execute(
                    select(EconomicCalendar)
                    .where(EconomicCalendar.impact == 'high')
                    .where(EconomicCalendar.event_time >= check_time - timedelta(hours=2))
                    .where(EconomicCalendar.event_time <= check_time + timedelta(hours=2))
                    .limit(1)
                )).scalar_one_or_none()
                return row is not None
        except Exception:
            return False

    async def _is_shock_only_strict(self, news: NewsItem) -> bool:
        """Fallback classifier konservatif."""
        text = self._text_for_classification(news).lower()
        if "breaking data:" in text:
            return True
        matches = [kw for kw in SHOCK_KEYWORDS if kw in text]
        if len(matches) >= 2:
            return True
        if len(matches) == 1:
            return await self._matches_recent_calendar_window(news)
        return False

    def _is_medium_impact(self, news: NewsItem) -> bool:
        """Mengembalikan True jika berita cocok dengan kata kunci Medium Impact."""
        text = self._text_for_classification(news)
        return bool(self._medium_re.search(text))

    def _get_affected_symbols(self, items: list[NewsItem]) -> list[str]:
        """
        Mengidentifikasi aset yang terdampak berita.
        Berdasarkan `currency_tags` dan pencarian teks judul.
        """
        affected = set()

        for news in items:
            # Use stored currency_tags first
            if news.currency_tags:
                for tag in news.currency_tags.split(","):
                    tag = tag.strip().upper()
                    for sym in CURRENCY_TO_SYMBOLS.get(tag, []):
                        affected.add(sym)

            # Fallback: scan title for currency mentions
            title_upper = (news.title or "").upper()
            for currency, symbols in CURRENCY_TO_SYMBOLS.items():
                if currency in title_upper:
                    affected.update(symbols)

        # Jika berita USD besar tanpa spesifik aset -> anggap semua aset USD terdampak
        text_combined = " ".join(
            self._text_for_classification(n) for n in items
        ).lower()
        if any(k in text_combined for k in ["federal reserve", "fomc", "fed rate", "powell"]):
            # USD news affects all instruments
            for syms in CURRENCY_TO_SYMBOLS.values():
                affected.update(syms)

        return sorted(affected)

    # ------------------------------------------------------------------
    # Re-analysis trigger
    # ------------------------------------------------------------------

    async def _trigger_reanalysis(
        self, high_items: list[NewsItem], affected_symbols: list[str], fallback_mode: bool = False
    ) -> None:
        # --- NEW: Check daily trade count before triggering ---
        from database.db import get_session
        from database.models import TradeOutcome, Position
        from sqlalchemy import select, func
        from datetime import timedelta
        
        try:
            async with get_session() as session_inner:
                # Record to Market Chronicle & generate immediate slice for breaking news
                try:
                    from analysis.memory.chronicle_writer import ChronicleWriter
                    from analysis.prefetch.digest_slice_generator import DigestSliceGenerator
                    c_writer = ChronicleWriter(self.settings)
                    slice_gen = DigestSliceGenerator(self.settings)
                    for h_item in high_items:
                        await c_writer.maybe_record_news_event(session_inner, h_item)
                    now_u = datetime.now(timezone.utc)
                    await slice_gen.generate_slice(session_inner, now_u - timedelta(hours=2), now_u, trigger='breaking')
                except Exception as e:
                    logger.debug(f"NewsWatcher chronicle/slice generation on breaking event failed (non-fatal): {e}")

                # Check open positions count
                open_pos_count = (await session_inner.execute(
                    select(func.count(Position.id)).where(Position.status == 'open')
                )).scalar_one_or_none() or 0
                logger.info(f"NewsWatcher: Triggering re-analysis for {len(high_items)} high-impact items. Open positions: {open_pos_count}")

                # Instant Jev System One shock evaluation for active positions
                if open_pos_count > 0:
                    try:
                        open_pos_records = (await session_inner.execute(
                            select(Position).where(Position.status == 'open')
                        )).scalars().all()
                        active_syms = list({p.symbol for p in open_pos_records if p.symbol})
                        for h_item in high_items:
                            shock = await self.evaluate_realtime_news_shock(h_item, open_positions=active_syms)
                            if shock and (shock.get("threatens_positions") or shock.get("requires_circuit_breaker")):
                                logger.warning(
                                    f"[NewsWatcher JevShock] Critical headline threat to positions {active_syms} "
                                    f"(threatens={shock.get('threatens_positions')}, breaker={shock.get('requires_circuit_breaker')}). "
                                    f"Tightening stops immediately."
                                )
                                await self._tighten_sl_on_breaking_news(active_syms)
                                break
                    except Exception as shock_err:
                        logger.debug(f"NewsWatcher Jev shock check error (non-fatal): {shock_err}")

                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)
                today_trades = (await session_inner.execute(
                    select(func.count(TradeOutcome.id))
                    .where(TradeOutcome.opened_at >= today_start)
                    .where(TradeOutcome.opened_at < today_end)
                )).scalar_one_or_none() or 0
                
                max_daily_trades = self.settings.get('trading', {}).get('risk', {}).get('max_daily_trades', 3)
                
                if today_trades >= max_daily_trades:
                    logger.info(
                        f'NewsWatcher: Daily trade limit reached ({today_trades}/{max_daily_trades}). '
                        f'Skipping Stage 2 reanalysis to save tokens — risk gate would block execution anyway.'
                    )
                    # Still run Stage 1 for macro brief update if it's a major news event
                    # but skip Stage 2 since it can't execute
                    if len(affected_symbols) >= 4 and self._fundamental_stage:
                        logger.info('Running Stage 1 only (major event) to update macro brief.')
                        async with get_session() as session:
                            await self._fundamental_stage.run(session, forced=True)
                    return
        except Exception as e:
            logger.debug(f'NewsWatcher daily count check failed (non-fatal): {e}')
        # --- END NEW ---
        """
        Memicu re-analisis saat ada breaking news.
        - Jika berdampak luas (>= 4 aset) -> Full Cycle.
        - Jika parsial -> Stage 1 singkat + Stage 2 spesifik aset.
        (Menerapkan batas harian rerun agar hemat budget)
        """
        all_assets = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"}
        affected_set = set(affected_symbols)

        # Dedup: if all high items are from calendar_poller and PostReleaseAnalyzer is active,
        # let PostReleaseAnalyzer handle the targeted Stage 2 re-analysis.
        if getattr(self, '_post_release_analyzer', None):
            calendar_items = [n for n in high_items if getattr(n, 'source', '') == 'calendar_poller']
            non_calendar = [n for n in high_items if getattr(n, 'source', '') != 'calendar_poller']
            if calendar_items and not non_calendar:
                logger.info(
                    "[NewsWatcher] All breaking items from calendar_poller — "
                    "PostReleaseAnalyzer handles targeted Stage 2 re-analysis. "
                    "Running emergency position protection only."
                )
                if self._position_guardian:
                    await self._position_guardian.check_and_protect(emergency=True)
                await self._tighten_sl_on_breaking_news(affected_symbols)
                return
            if non_calendar:
                high_items = non_calendar

        # --- Circuit breaker: reset counter on new UTC day ---
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._forced_rerun_day != today_utc:
            self._forced_rerun_day = today_utc
            self._forced_reruns_today = 0

        # Coalesce event into active turn leases if active
        try:
            from agent.turn_lease_manager import SymbolTurnLeaseManager
            lease_mgr = SymbolTurnLeaseManager.get_instance()
            top_title = high_items[0].title if high_items else "Breaking News Shock"
            coalesce_msg = (
                f"[BREAKING NEWS SHOCK] {top_title}. "
                f"Immediate market volatility catalyst detected. "
                f"Re-evaluate current bias, technical validity, and risk parameters."
            )
            coalesced_symbols = []
            for sym in list(affected_symbols):
                if await lease_mgr.coalesce_event(sym, coalesce_msg, sender="news_watcher"):
                    coalesced_symbols.append(sym)
            if coalesced_symbols:
                logger.info(
                    f"NewsWatcher: Successfully coalesced breaking shock into active analysis turns for {coalesced_symbols}."
                )
                affected_symbols = [s for s in affected_symbols if s not in coalesced_symbols]
                affected_set = set(affected_symbols)
                if not affected_symbols:
                    logger.info("NewsWatcher: All affected symbols coalesced into active turns. Skipping redundant rerun.")
                    return
        except Exception as lease_err:
            logger.debug(f"NewsWatcher: Event coalescence check non-fatal error: {lease_err}")

        want_full_cycle = (affected_set >= all_assets or len(affected_symbols) >= 4) and not fallback_mode
        if fallback_mode and (affected_set >= all_assets or len(affected_symbols) >= 4):
            logger.warning('Fallback mode aktif — full-cycle rerun DITOLAK meski affected_symbols besar. Downgrade ke targeted rerun per-simbol saja.')

        POST_EVENT_DELAY_MINUTES = 15
        
        if want_full_cycle and self._forced_reruns_today < self._max_forced_reruns:
            # Full cycle re-run (within budget)
            self._forced_reruns_today += 1
            logger.info(
                f"Breaking news: triggering full analysis cycle "
                f"({self._forced_reruns_today}/{self._max_forced_reruns} today). "
                f"Waiting {POST_EVENT_DELAY_MINUTES}min for market to settle..."
            )
            if self._position_guardian:
                logger.info('Breaking news: running emergency position check...')
                await self._position_guardian.check_and_protect(emergency=True)
            await self._tighten_sl_on_breaking_news(affected_symbols)
            await asyncio.sleep(POST_EVENT_DELAY_MINUTES * 60)
            
            if self._cycle_scheduler:
                asyncio.create_task(self._cycle_scheduler.run_once(forced=True))
            return

        if want_full_cycle and self._forced_reruns_today >= self._max_forced_reruns:
            logger.warning(
                f"Breaking news: full-cycle rerun budget exhausted "
                f"({self._forced_reruns_today}/{self._max_forced_reruns}). "
                f"Downgrading to targeted Stage-2 reruns for {affected_symbols}."
            )
            # Fall through to partial re-run below

        # For targeted Stage 2 reruns, apply per-symbol cooldown:
        now = datetime.now(timezone.utc)
        symbols_to_reanalyze = []
        
        for sym in affected_symbols:
            last_time = self._last_reanalysis.get(sym)
            if last_time is None:
                symbols_to_reanalyze.append(sym)
                self._last_reanalysis[sym] = now
            else:
                elapsed_minutes = (now - last_time).total_seconds() / 60
                if elapsed_minutes >= self._min_reanalysis_interval_minutes:
                    symbols_to_reanalyze.append(sym)
                    self._last_reanalysis[sym] = now
                else:
                    logger.info(
                        f'News watcher: Skipping {sym} reanalysis '
                        f'({elapsed_minutes:.0f}min < {self._min_reanalysis_interval_minutes}min cooldown)'
                    )
        
        if not symbols_to_reanalyze:
            logger.info('All affected symbols in cooldown period. No targeted reanalysis triggered.')
            return

        if self._targeted_reruns_today >= self._max_targeted_reruns:
            logger.warning(
                f"Breaking news: targeted rerun budget exhausted "
                f"({self._targeted_reruns_today}/{self._max_targeted_reruns}). "
                f"Skipping targeted Stage-2 reruns for {symbols_to_reanalyze} to preserve budget."
            )
            return

        self._targeted_reruns_today += 1

        # Partial: Stage 1 (if not budget-capped full cycle) + targeted Stage 2
        logger.info(
            f"Breaking news: running Stage 1 + Stage 2 for {symbols_to_reanalyze}. "
            f"Targeted rerun budget: {self._targeted_reruns_today}/{self._max_targeted_reruns}. "
            f"Waiting {POST_EVENT_DELAY_MINUTES}min for market to settle..."
        )
        if self._position_guardian:
            logger.info('Breaking news: running emergency position check...')
            await self._position_guardian.check_and_protect(emergency=True)
        await self._tighten_sl_on_breaking_news(symbols_to_reanalyze)
        await asyncio.sleep(POST_EVENT_DELAY_MINUTES * 60)
        
        post_event_context = (
            f'\n\nPOST-EVENT CONTEXT: This analysis is triggered {POST_EVENT_DELAY_MINUTES} minutes '
            f'after breaking news: {high_items[0].title[:100]}. '
            f'This is a POST-EVENT window — highest quality entry opportunity. '
            f'Look for: (1) Initial spike reversal, (2) Re-test of pre-news level, '
            f'(3) Structure reset with fresh FVG/OB created by the news spike.'
        )

        cycle_lock = getattr(self._cycle_scheduler, '_cycle_lock', None) if self._cycle_scheduler else None
        if cycle_lock:
            async with cycle_lock:
                if self._fundamental_stage:
                    async with get_session() as session:
                        await self._fundamental_stage.run(session, forced=True)

                if self._per_asset_stage and symbols_to_reanalyze:
                    await self._run_targeted_reanalysis_and_route(
                        symbols=symbols_to_reanalyze,
                        context=post_event_context
                    )
        else:
            if self._fundamental_stage:
                async with get_session() as session:
                    await self._fundamental_stage.run(session, forced=True)

            if self._per_asset_stage and symbols_to_reanalyze:
                await self._run_targeted_reanalysis_and_route(
                    symbols=symbols_to_reanalyze,
                    context=post_event_context
                )

    async def _run_targeted_reanalysis_and_route(self, symbols: list[str], context: str) -> None:
        """Run targeted per-asset reanalysis and route actionable trades to execution."""
        if self._per_asset_stage is None:
            return
        from database.db import get_session as _gs
        from agent.turn_lease_manager import SymbolTurnLeaseManager

        lease_mgr = SymbolTurnLeaseManager.get_instance()
        holder_id = f"news_watcher_{int(datetime.now(timezone.utc).timestamp())}"
        acquired_symbols = []

        try:
            for sym in symbols:
                if await lease_mgr.acquire_lease(sym, holder_id=holder_id, ttl_seconds=300.0):
                    acquired_symbols.append(sym)

            pa_results = await self._per_asset_stage.run_all(
                session_factory=_gs,
                symbols=symbols,
                is_secondary=True,
                use_session_trigger_client=True,
                extra_context=context,
                skip_cooldown=True
            )
            actionable = [
                (sym, r) for sym, r in pa_results.items()
                if isinstance(r, dict) and r.get('decision') in ('buy', 'sell') and r.get('analysis_id')
            ] if isinstance(pa_results, dict) else []
            if actionable:
                logger.info(f"[NewsWatcher] Found {len(actionable)} actionable trade(s) from news reanalysis: {actionable}")
                # LangGraph Reactive Entry Point (CRITICAL-01)
                try:
                    from graph.reactive_graph import get_reactive_graph
                    reactive_graph = get_reactive_graph()
                    scheduler_ctx = self._cycle_scheduler or self
                    reactive_state = {
                        "symbols": symbols,
                        "actionable_trades": actionable,
                        "event_type": "news_event",
                        "extra_context": context,
                        "event_data": {"source": "news_watcher", "symbols": symbols},
                        "market_regime": "normal",
                        "summary": {},
                        "errors": [],
                        "should_pause": False,
                    }
                    config = {"configurable": {"scheduler": scheduler_ctx}}
                    logger.info("[NewsWatcher] Routing actionable trades through LangGraph ReactiveStateGraph...")
                    await reactive_graph.ainvoke(reactive_state, config=config)
                except Exception as e:
                    logger.error(f"[NewsWatcher] LangGraph reactive execution failed: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[NewsWatcher] Targeted reanalysis failed: {e}")
        finally:
            for sym in acquired_symbols:
                await lease_mgr.release_lease(sym, holder_id=holder_id)

    async def _tighten_sl_on_breaking_news(self, affected_symbols: list[str]) -> None:
        """
        Memperketat Stop Loss ke level Breakeven (atau entry + buffer) untuk posisi terbuka
        pada aset yang terdampak saat rilis breaking news, sebelum jeda 15 menit.
        """
        if not self._execution_service or not affected_symbols:
            return
        try:
            from database.db import get_session
            from database.models import Position
            from sqlalchemy import select
            
            async with get_session() as session:
                positions = (await session.execute(
                    select(Position)
                    .where(Position.status == 'open')
                    .where(Position.symbol.in_(affected_symbols))
                )).scalars().all()

                for pos in positions:
                    if not pos.mt5_ticket:
                        continue
                    direction = (pos.direction or '').lower()
                    entry = pos.entry_price
                    current_sl = pos.sl

                    if not entry:
                        continue

                    # Fetch live quote to verify position is in profit before moving SL to breakeven
                    current_price = None
                    if hasattr(self._execution_service, "get_current_price"):
                        try:
                            current_price = await self._execution_service.get_current_price(pos.symbol)
                        except Exception:
                            pass
                    if current_price is None and hasattr(self._execution_service, "mt5"):
                        try:
                            tick = await self._execution_service.mt5.get_current_price(pos.symbol)
                            if isinstance(tick, dict):
                                current_price = tick.get("bid") if direction == "buy" else tick.get("ask")
                        except Exception:
                            pass
                    pos_curr_price = getattr(pos, "current_price", None)
                    if current_price is None and pos_curr_price is not None:
                        current_price = float(pos_curr_price)

                    should_tighten = False
                    new_sl: Optional[float] = None
                    if current_price is not None:
                        # Only tighten to BE if position is currently in profit (avoid MT5 INVALID_STOPS rejection)
                        if direction == 'buy' and current_price > entry:
                            if current_sl is None or current_sl < entry:
                                should_tighten = True
                                new_sl = entry
                        elif direction == 'sell' and current_price < entry:
                            if current_sl is None or current_sl > entry:
                                should_tighten = True
                                new_sl = entry

                    if should_tighten and new_sl is not None and hasattr(self._execution_service, 'modify_position_sl_tp'):
                        try:
                            await self._execution_service.modify_position_sl_tp(
                                ticket=pos.mt5_ticket, sl=new_sl, tp=pos.tp, requested_by="news_watcher"
                            )
                            logger.info(f"NewsWatcher: Tightened SL to breakeven ({new_sl}) for {pos.symbol} ticket={pos.mt5_ticket} due to breaking news")
                        except Exception as e:
                            logger.warning(f"NewsWatcher: Failed tightening SL for {pos.symbol}: {e}")
        except Exception as e:
            logger.debug(f"NewsWatcher SL tighten error (non-fatal): {e}")

    async def evaluate_realtime_news_shock(self, news_item: Any, open_positions: Optional[list] = None) -> dict:
        """Instant sub-100ms news impact & position threat assessment via TypeSafe Jev System One."""
        try:
            from analysis.providers.llm_factory import get_client_for_task
            from utils.typesafe.jev_primitives import build_realtime_news_questions
            client = get_client_for_task("jev_news_realtime", self.settings)
            questions = build_realtime_news_questions(open_positions=open_positions)
            state = {
                "title": str(getattr(news_item, "title", "") or "")[:300],
                "summary": str(getattr(news_item, "summary", "") or "")[:1000],
                "open_positions": open_positions or []
            }
            res = await client.classify_json(prompt="", state=state, jev_questions=questions)
            return res or {}
        except Exception as e:
            logger.debug(f"Realtime news shock evaluation bypassed: {e}")
            return {}

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    async def _log(
        self, session: AsyncSession, description: str, category: str = "analysis"
    ) -> None:
        try:
            session.add(ActivityLog(
                category=category,
                description=description,
                actor="news_watcher",
            ))
            await session.commit()
        except Exception as e:
            logger.debug(f"Log write failed (non-fatal): {e}")

