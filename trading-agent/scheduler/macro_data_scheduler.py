# ==============================================================================
# File: scheduler/macro_data_scheduler.py
# ==============================================================================

"""
Macro Data Scheduler: Worker independen untuk ingestion data makro & sentimen berkala.

Fungsi:
1. Menjaga data makro (VIX, DXY, FRED Yields, CFTC COT, Bond Yields, EIA) dan sentimen
   (Fear & Greed, Coinglass, Binance, MyFxBook, FXSSI) selalu mutakhir (default 30 menit).
2. Terpisah dari GraphCycleScheduler (siklus 6-8 jam) sehingga NewsWatcher,
   TriggerChecker, dan Telegram ChatAgent selalu membaca data makro segar.
3. Menyediakan method `refresh_macro_data()` yang aman dan terisolasi per data source.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from database.db import get_session

logger = logging.getLogger("TradingAgent.MacroDataScheduler")


class MacroDataScheduler:
    """
    Background worker mandiri untuk me-refresh 11 sumber data makro & sentimen.
    """
    _global_sync_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_global_lock(cls) -> asyncio.Lock:
        if cls._global_sync_lock is None:
            cls._global_sync_lock = asyncio.Lock()
        return cls._global_sync_lock

    def __init__(self, settings: dict):
        self.settings = settings
        sched_cfg = settings.get("trading", {}).get("schedule", {})
        self.interval_minutes: float = float(sched_cfg.get("macro_data_refresh_minutes", 30))
        self._running = False
        self._stop_event = asyncio.Event()
        self._sync_lock = self._get_global_lock()
        self._last_refresh_time: Optional[datetime] = None
        self._last_results: Dict[str, Any] = {}

    async def refresh_macro_data(self) -> Dict[str, Any]:
        """
        Menjalankan ingestion untuk 11 sumber data makro dan sentimen secara aman.
        """
        lock = self._get_global_lock()
        if lock.locked():
            logger.debug("MacroDataScheduler: Ingestion already in progress, skipping concurrent run.")
            return {"status": "in_progress", "reason": "already_running"}

        async with lock:
            results: Dict[str, Any] = {}
            logger.info("MacroDataScheduler: Starting 30-minute macro/sentiment data ingestion...")

            # 1. Coinglass Funding
            try:
                from data_sources.coinglass_funding import CoinglasFundingFetcher
                async with get_session() as session:
                    fetcher = CoinglasFundingFetcher(session)
                    fg = await fetcher.fetch()
                    results['btc_funding'] = fg
                    logger.info("MacroDataScheduler: Coinglass funding refreshed")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: Coinglass funding fetch failed: {e}")
                results['btc_funding'] = {'error': str(e)}

            # 2. Binance Sentiment
            try:
                from scrapers.sentiment.binance_sentiment import BinanceSentimentFetcher
                async with get_session() as session:
                    fetcher = BinanceSentimentFetcher(session)
                    sentiment = await fetcher.fetch()
                    results['binance_sentiment'] = sentiment
                    logger.info("MacroDataScheduler: Binance retail sentiment refreshed")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: Binance sentiment fetch failed: {e}")
                results['binance_sentiment'] = {'error': str(e)}

            # 3. MyFxBook Sentiment
            try:
                from scrapers.sentiment.myfxbook_sentiment import MyFxBookSentimentFetcher
                async with get_session() as session:
                    fetcher = MyFxBookSentimentFetcher(session)
                    sentiment = await fetcher.fetch()
                    results['myfxbook_sentiment'] = sentiment
                    logger.info("MacroDataScheduler: MyFxBook retail sentiment refreshed")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: MyFxBook sentiment fetch failed: {e}")
                results['myfxbook_sentiment'] = {'error': str(e)}

            # 4. FXSSI Sentiment
            try:
                from scrapers.sentiment.fxssi_sentiment import FXSSISentimentFetcher
                async with get_session() as session:
                    fetcher = FXSSISentimentFetcher(session)
                    sentiment = await fetcher.fetch()
                    results['fxssi_sentiment'] = sentiment
                    logger.info("MacroDataScheduler: FXSSI retail sentiment refreshed")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: FXSSI sentiment fetch failed: {e}")
                results['fxssi_sentiment'] = {'error': str(e)}

            # 5. VIX (Yahoo Finance)
            try:
                from data_sources.vix_yfinance import VIXFetcher
                async with get_session() as session:
                    fetcher = VIXFetcher(session)
                    n = await fetcher.fetch(period='5d')
                    results['vix'] = {'saved': n}
                    logger.info(f"MacroDataScheduler: VIX refreshed ({n} records)")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: VIX refresh failed: {e}")
                results['vix'] = {'error': str(e)}

            # 6. FRED Treasury Yields
            try:
                from data_sources.fred_treasury_yield import FREDDataFetcher
                async with get_session() as session:
                    fetcher = FREDDataFetcher(session, self.settings.get('data_sources', {}).get('fred', {}))
                    r = await fetcher.fetch_all()
                    results['fred'] = r
                    logger.info(f"MacroDataScheduler: FRED refreshed: {r}")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: FRED refresh failed: {e}")
                results['fred'] = {'error': str(e)}

            # 7. CFTC COT Report
            try:
                from data_sources.cftc_cot import CFTCCOTFetcher
                async with get_session() as session:
                    fetcher = CFTCCOTFetcher(session, self.settings.get('data_sources', {}).get('cftc_cot', {}))
                    n = await fetcher.fetch_all()
                    results['cftc'] = {'saved': n}
                    logger.info(f"MacroDataScheduler: CFTC COT refreshed ({n} records)")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: CFTC refresh failed: {e}")
                results['cftc'] = {'error': str(e)}

            # 8. DXY (Yahoo Finance)
            try:
                from data_sources.dxy_yfinance import DXYFetcher
                async with get_session() as session:
                    fetcher = DXYFetcher(session)
                    n = await fetcher.fetch(period='15d')
                    results['dxy'] = {'saved': n}
                    logger.info(f"MacroDataScheduler: DXY refreshed ({n} records)")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: DXY refresh failed: {e}")
                results['dxy'] = {'error': str(e)}

            # 9. Bond Yields (Yahoo Finance)
            try:
                from data_sources.bond_yields_fetcher import BondYieldFetcher
                async with get_session() as session:
                    fetcher = BondYieldFetcher(session)
                    r = await fetcher.fetch(period='15d')
                    results['bond_yields'] = r
                    logger.info(f"MacroDataScheduler: Bond yields refreshed: {r}")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: Bond yields refresh failed: {e}")
                results['bond_yields'] = {'error': str(e)}

            # 10. Crypto Fear & Greed Index
            try:
                from data_sources.fear_greed import FearGreedFetcher
                async with get_session() as session:
                    fetcher = FearGreedFetcher(session)
                    fg = await fetcher.fetch()
                    results['fear_greed'] = {
                        'value': fg.get('current_value'),
                        'classification': fg.get('classification')
                    }
                    logger.info(f"MacroDataScheduler: Fear & Greed refreshed ({fg.get('current_value')})")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: Fear & Greed fetch failed: {e}")
                results['fear_greed'] = {'error': str(e)}

            # 11. EIA Oil Inventory
            try:
                from data_sources.eia_oil_inventory import EIAInventoryFetcher
                is_wednesday = datetime.now(timezone.utc).weekday() == 2
                if is_wednesday:
                    async with get_session() as session:
                        fetcher = EIAInventoryFetcher(session)
                        eia = await fetcher.fetch()
                        results['eia_oil'] = eia
                        logger.info("MacroDataScheduler: EIA Oil inventory refreshed")
                else:
                    results['eia_oil'] = {'status': 'skipped_not_wednesday'}
            except Exception as e:
                logger.warning(f"MacroDataScheduler: EIA fetch failed: {e}")
                results['eia_oil'] = {'error': str(e)}

            # 12. Central Bank Watch Rate Expectations & Sovereign Curves (Fed, ECB, BoE, BoJ, RBA)
            try:
                from data_sources.central_bank_watch import CentralBankWatchFetcher
                async with get_session() as session:
                    fetcher = CentralBankWatchFetcher(session)
                    cbw = await fetcher.fetch_all()
                    results['central_bank_watch'] = {
                        'expectations_count': len(cbw.get('expectations', {})),
                        'yields_count': len(cbw.get('yields', {})),
                    }
                    logger.info(f"MacroDataScheduler: Central Bank Watch refreshed ({len(cbw.get('expectations', {}))} banks, {len(cbw.get('yields', {}))} curves)")
            except Exception as e:
                logger.warning(f"MacroDataScheduler: Central Bank Watch fetch failed: {e}")
                results['central_bank_watch'] = {'error': str(e)}

            self._last_refresh_time = datetime.now(timezone.utc)
            self._last_results = results
            logger.info("MacroDataScheduler: Ingestion cycle completed for all 12 sources.")
            return results

    async def start(self) -> None:
        """Loop eksekusi periodik MacroDataScheduler."""
        self._running = True
        interval_secs = max(60.0, self.interval_minutes * 60.0)
        logger.info(f"MacroDataScheduler: Started with interval={self.interval_minutes} minutes ({interval_secs}s).")

        # Initial refresh on startup (brief delay to allow DB/network stabilization)
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=5)
            return
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            return

        try:
            await self.refresh_macro_data()
        except Exception as init_err:
            logger.warning(f"MacroDataScheduler: Initial ingestion error (non-fatal): {init_err}")

        while self._running:
            try:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval_secs)
                    break
                except asyncio.TimeoutError:
                    pass
                if not self._running:
                    break
                await self.refresh_macro_data()
            except asyncio.CancelledError:
                logger.info("MacroDataScheduler: Cancellation requested. Stopping...")
                self._running = False
                break
            except Exception as loop_err:
                logger.error(f"MacroDataScheduler: Unexpected error in run loop: {loop_err}", exc_info=True)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=30)
                    break
                except asyncio.TimeoutError:
                    pass

    def stop(self) -> None:
        """Menghentikan worker."""
        self._running = False
        self._stop_event.set()
