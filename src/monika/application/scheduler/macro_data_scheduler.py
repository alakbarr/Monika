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
from typing import Any, Dict, Optional

from monika.infrastructure.database.db import get_session

logger = logging.getLogger("TradingAgent.MacroDataScheduler")


class MacroDataScheduler:
    """
    Background worker mandiri untuk me-refresh 11 sumber data makro & sentimen.
    """

    _global_sync_locks: dict[Any, asyncio.Lock] = {}
    FETCH_TIMEOUT_SECS: float = 90.0

    def _fmt_err(self, e: Exception) -> str:
        msg = str(e).strip()
        if msg:
            return msg
        if isinstance(e, TimeoutError):
            return f"TimeoutError (exceeded {self.FETCH_TIMEOUT_SECS:.0f}s)"
        return type(e).__name__

    @classmethod
    def _get_global_lock(cls) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop not in cls._global_sync_locks:
            cls._global_sync_locks[loop] = asyncio.Lock()
        return cls._global_sync_locks[loop]

    def __init__(self, settings: dict, recovery_event: Optional[asyncio.Event] = None):
        self.settings = settings
        sched_cfg = settings.get("trading", {}).get("schedule", {})
        self.interval_minutes: float = float(sched_cfg.get("macro_data_refresh_minutes", 30))
        self._running = False
        self._stop_event = asyncio.Event()
        self._sync_lock = self._get_global_lock()
        self._last_refresh_time: Optional[datetime] = None
        self._last_results: Dict[str, Any] = {}
        self.recovery_event = recovery_event

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
                from monika.infrastructure.data_ingestion.sources.coinglass_funding import CoinglasFundingFetcher

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = CoinglasFundingFetcher(session)
                        fg = await fetcher.fetch()
                        results["btc_funding"] = fg
                        logger.info("MacroDataScheduler: Coinglass funding refreshed")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: Coinglass funding fetch failed: {err_msg}")
                results["btc_funding"] = {"error": err_msg}

            # 2. Binance Sentiment
            try:
                from monika.infrastructure.data_ingestion.scrapers.sentiment.binance_sentiment import (
                    BinanceSentimentFetcher,
                )

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = BinanceSentimentFetcher(session)
                        sentiment = await fetcher.fetch()
                        results["binance_sentiment"] = sentiment
                        logger.info("MacroDataScheduler: Binance retail sentiment refreshed")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: Binance sentiment fetch failed: {err_msg}")
                results["binance_sentiment"] = {"error": err_msg}

            # 3. MyFxBook Sentiment
            try:
                from monika.infrastructure.data_ingestion.scrapers.sentiment.myfxbook_sentiment import (
                    MyFxBookSentimentFetcher,
                )

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = MyFxBookSentimentFetcher(session)
                        sentiment = await fetcher.fetch()
                        results["myfxbook_sentiment"] = sentiment
                        logger.info("MacroDataScheduler: MyFxBook retail sentiment refreshed")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: MyFxBook sentiment fetch failed: {err_msg}")
                results["myfxbook_sentiment"] = {"error": err_msg}

            # 4. FXSSI Sentiment
            try:
                from monika.infrastructure.data_ingestion.scrapers.sentiment.fxssi_sentiment import (
                    FXSSISentimentFetcher,
                )

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = FXSSISentimentFetcher(session)
                        sentiment = await fetcher.fetch()
                        results["fxssi_sentiment"] = sentiment
                        logger.info("MacroDataScheduler: FXSSI retail sentiment refreshed")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: FXSSI sentiment fetch failed: {err_msg}")
                results["fxssi_sentiment"] = {"error": err_msg}

            # 5. VIX (Multi-tier: Yahoo Direct, CBOE CDN, FRED, yfinance)
            try:
                from monika.infrastructure.data_ingestion.sources.vix_yfinance import VIXFetcher

                fred_key = self.settings.get("data_sources", {}).get("fred", {}).get("api_key")
                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = VIXFetcher(session, fred_api_key=fred_key)
                        n = await fetcher.fetch(period="5d")
                        results["vix"] = {"saved": n}
                        logger.info(f"MacroDataScheduler: VIX refreshed ({n} records)")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: VIX refresh failed: {err_msg}")
                results["vix"] = {"error": err_msg}

            # 6. FRED Treasury Yields
            try:
                from monika.infrastructure.data_ingestion.sources.fred_treasury_yield import FREDDataFetcher

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = FREDDataFetcher(session, self.settings.get("data_sources", {}).get("fred", {}))
                        r = await fetcher.fetch_all()
                        results["fred"] = r
                        logger.info(f"MacroDataScheduler: FRED refreshed: {r}")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: FRED refresh failed: {err_msg}")
                results["fred"] = {"error": err_msg}

            # 7. CFTC COT Report
            try:
                from monika.infrastructure.data_ingestion.sources.cftc_cot import CFTCCOTFetcher

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = CFTCCOTFetcher(session, self.settings.get("data_sources", {}).get("cftc_cot", {}))
                        n = await fetcher.fetch_all()
                        results["cftc"] = {"saved": n}
                        logger.info(f"MacroDataScheduler: CFTC COT refreshed ({n} records)")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: CFTC refresh failed: {err_msg}")
                results["cftc"] = {"error": err_msg}

            # 8. DXY (Yahoo Finance)
            try:
                from monika.infrastructure.data_ingestion.sources.dxy_yfinance import DXYFetcher

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = DXYFetcher(session)
                        n = await fetcher.fetch(period="15d")
                        results["dxy"] = {"saved": n}
                        logger.info(f"MacroDataScheduler: DXY refreshed ({n} records)")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: DXY refresh failed: {err_msg}")
                results["dxy"] = {"error": err_msg}

            # 9. Bond Yields (Yahoo Finance)
            try:
                from monika.infrastructure.data_ingestion.sources.bond_yields_fetcher import BondYieldFetcher

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = BondYieldFetcher(session)
                        r = await fetcher.fetch(period="15d")
                        results["bond_yields"] = r
                        logger.info(f"MacroDataScheduler: Bond yields refreshed: {r}")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: Bond yields refresh failed: {err_msg}")
                results["bond_yields"] = {"error": err_msg}

            # 10. Crypto Fear & Greed Index
            try:
                from monika.infrastructure.data_ingestion.sources.fear_greed import FearGreedFetcher

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = FearGreedFetcher(session)
                        fg = await fetcher.fetch()
                        results["fear_greed"] = {
                            "value": fg.get("current_value"),
                            "classification": fg.get("classification"),
                        }
                        logger.info(f"MacroDataScheduler: Fear & Greed refreshed ({fg.get('current_value')})")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: Fear & Greed fetch failed: {err_msg}")
                results["fear_greed"] = {"error": err_msg}

            # 11. EIA Oil Inventory
            try:
                from monika.infrastructure.data_ingestion.sources.eia_oil_inventory import EIAInventoryFetcher

                is_wednesday = datetime.now(timezone.utc).weekday() == 2
                if is_wednesday:
                    async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                        async with get_session() as session:
                            fetcher = EIAInventoryFetcher(session)
                            eia = await fetcher.fetch()
                            results["eia_oil"] = eia
                            logger.info("MacroDataScheduler: EIA Oil inventory refreshed")
                else:
                    results["eia_oil"] = {"status": "skipped_not_wednesday"}
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: EIA fetch failed: {err_msg}")
                results["eia_oil"] = {"error": err_msg}

            # 12. Central Bank Watch Rate Expectations & Sovereign Curves (Fed, ECB, BoE, BoJ, RBA)
            try:
                from monika.infrastructure.data_ingestion.sources.central_bank_watch import CentralBankWatchFetcher

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fetcher = CentralBankWatchFetcher(session)
                        cbw = await fetcher.fetch_all()
                        results["central_bank_watch"] = {
                            "expectations_count": len(cbw.get("expectations", {})),
                            "yields_count": len(cbw.get("yields", {})),
                        }
                        logger.info(
                            f"MacroDataScheduler: Central Bank Watch refreshed ({len(cbw.get('expectations', {}))} banks, {len(cbw.get('yields', {}))} curves)"
                        )
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: Central Bank Watch fetch failed: {err_msg}")
                results["central_bank_watch"] = {"error": err_msg}

            # 13. Fed H.4.1 Net Liquidity, Treasury Auctions & Market Stress
            try:
                from monika.infrastructure.data_ingestion.sources.fed_liquidity_h41_fetcher import (
                    FedLiquidityH41Fetcher,
                )
                from monika.infrastructure.data_ingestion.sources.market_stress_auction_fetcher import (
                    MarketStressAuctionFetcher,
                )

                fred_key = self.settings.get("data_sources", {}).get("fred", {}).get("api_key")
                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        fed_fetcher = FedLiquidityH41Fetcher(session, api_key=fred_key)
                        stress_fetcher = MarketStressAuctionFetcher(session, api_key=fred_key)
                        fed_res = await fed_fetcher.fetch_and_store_liquidity()
                        auc_res = await stress_fetcher.fetch_and_store_treasury_auction(tenor="10Y")
                        stress_res = await stress_fetcher.fetch_and_store_credit_and_money_market()

                    net_liq = fed_res.get("net_liquidity_billions")
                    auc_yield = auc_res.get("value")
                    results["systemic_liquidity_and_stress"] = {
                        "net_liquidity_b": net_liq,
                        "auction_yield": auc_yield,
                        "stress_metrics": len(stress_res),
                    }
                    net_liq_str = f"${net_liq:,.1f}B" if net_liq is not None else "unavailable"
                    auc_str = f"{auc_yield:.3f}%" if auc_yield is not None else "unavailable"
                    logger.info(
                        f"MacroDataScheduler: Fed Net Liquidity ({net_liq_str}) and Treasury Auction ({auc_str}) refreshed"
                    )
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: Systemic liquidity refresh failed: {err_msg}")
                results["systemic_liquidity_and_stress"] = {"error": err_msg}

            # 14. Central Bank Documents & Macro Decomposition Warmup
            try:
                from monika.infrastructure.data_ingestion.scrapers.macro.macro_trigger_router import MacroTriggerRouter

                async with asyncio.timeout(self.FETCH_TIMEOUT_SECS):
                    async with get_session() as session:
                        router = MacroTriggerRouter(session)
                        await router.ensure_cb_document_available(bank="FED", doc_type="MINUTES")
                        await router.ensure_cb_document_available(bank="FED", doc_type="STATEMENT")
                        await router.ensure_cb_document_available(bank="ECB", doc_type="STATEMENT")
                        await router.ensure_cb_document_available(bank="BOJ", doc_type="STATEMENT")
                        await router.ensure_report_available(report_type="CPI")
                        await router.ensure_report_available(report_type="NFP")
                        results["macro_docs_and_decomposition"] = {"status": "verified_and_warmed"}
                        logger.info("MacroDataScheduler: Central bank documents and macro decomposition cache warmed")
            except Exception as e:
                err_msg = self._fmt_err(e)
                logger.warning(f"MacroDataScheduler: Central bank docs warm failed: {err_msg}")
                results["macro_docs_and_decomposition"] = {"error": err_msg}

            self._last_refresh_time = datetime.now(timezone.utc)
            self._last_results = results
            logger.info("MacroDataScheduler: Ingestion cycle completed for all 14 sources.")
            return results

    async def start(self) -> None:
        """Loop eksekusi periodik MacroDataScheduler."""
        self._running = True
        interval_secs = max(60.0, self.interval_minutes * 60.0)
        logger.info(f"MacroDataScheduler: Started with interval={self.interval_minutes} minutes ({interval_secs}s).")

        # Initial refresh on startup (tunggu startup recovery jika ada, agar tidak bersaing CPU/network dengan bootstrap)
        if self.recovery_event:
            logger.info("MacroDataScheduler: Waiting for recovery event before initial ingestion...")
            try:
                await asyncio.wait_for(self.recovery_event.wait(), timeout=180.0)
                logger.info("MacroDataScheduler: Recovery complete, proceeding with initial ingestion.")
            except asyncio.TimeoutError:
                logger.warning("MacroDataScheduler: Recovery event timed out (180s), proceeding anyway.")
            except asyncio.CancelledError:
                return
        else:
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
