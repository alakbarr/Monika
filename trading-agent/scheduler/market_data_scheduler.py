# ==============================================================================
# File: scheduler/market_data_scheduler.py
# ==============================================================================

"""
Market Data Scheduler: Penjadwal sinkronisasi berkala data pasar (OHLCV & Indikator).

Fungsi:
1. Menjaga tabel PriceOHLCV dan TechnicalIndicator di database selalu mutakhir
   secara independen di luar siklus 6-jam LangGraph.
2. Menyediakan method `sync_now()` untuk sinkronisasi on-demand (saat startup
   dan auto-healing pasca pemulihan koneksi internet/MT5).
3. Mencegah error data freshness pada fast runners (EdgeStrategyRunner,
   PaperTradeMonitor, TriggerChecker, TrailingStopManager).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_session
from indicators.technical import TechnicalIndicatorCalculator
from indicators.structure import MarketStructureAnalyzer
from utils.validation.data_validator import is_forex_market_closed, is_crypto_symbol

logger = logging.getLogger("TradingAgent.MarketDataScheduler")


class MarketDataScheduler:
    """
    Background worker untuk sinkronisasi data pasar MT5 berkala.
    """

    def __init__(self, settings: dict, mt5_client: Optional[Any] = None, event_bus: Optional[Any] = None):
        self.settings = settings
        self._mt5 = mt5_client
        self.event_bus = event_bus
        self._running = False
        self._stop_event = asyncio.Event()
        self._sync_lock = asyncio.Lock()

        sched_cfg = settings.get("trading", {}).get("schedule", {})
        self.interval_seconds = int(sched_cfg.get("market_data_sync_interval_seconds", 180))  # Default 3 menit
        self.asset_universe: list[str] = settings.get("trading", {}).get("asset_universe", ["XAUUSD", "EURUSD"])
        
        mt5_cfg = settings.get("trading", {}).get("mt5", {})
        self.timeframes: list[str] = mt5_cfg.get("timeframes", ["M15", "H1", "H4", "D1"])
        self._last_sync_time: Optional[datetime] = None

    async def sync_now(self, session: Optional[AsyncSession] = None) -> dict:
        """
        Menjalankan sinkronisasi data pasar instan untuk semua simbol dan timeframe aktif.
        Dapat dipanggil saat startup, setelah reconnect internet, atau secara periodik.
        """
        if self._sync_lock.locked():
            logger.debug("[MarketDataSync] Sinkronisasi sedang berlangsung, melewati panggilan bersamaan.")
            return {"status": "in_progress", "reason": "sync_already_running"}

        async with self._sync_lock:
            if not self._mt5:
                logger.warning("[MarketDataSync] MT5 client tidak tersedia, sinkronisasi dibatalkan.")
                return {"status": "skipped", "reason": "no_mt5_client"}

            # Pastikan koneksi MT5 aktif
            if not await self._mt5.ensure_connected():
                logger.warning("[MarketDataSync] MT5 offline, tidak dapat mengambil data pasar.")
                return {"status": "failed", "reason": "mt5_disconnected"}

            now_utc = datetime.now(timezone.utc)
            forex_closed = is_forex_market_closed(now_utc)

            # Tentukan simbol target (jika weekend, prioritaskan aset crypto 24/7)
            target_symbols = self.asset_universe
            if forex_closed:
                crypto_symbols = [s for s in self.asset_universe if is_crypto_symbol(s)]
                if crypto_symbols:
                    target_symbols = crypto_symbols
                    logger.debug(f"[MarketDataSync] Pasar forex tutup. Menyelaraskan crypto saja: {crypto_symbols}")
                else:
                    logger.debug("[MarketDataSync] Pasar forex tutup dan tidak ada simbol crypto. Sinkronisasi dilewati.")
                    return {"status": "skipped", "reason": "market_closed"}

            summary = {"started_at": now_utc.isoformat(), "price_fetch": {}, "indicators": {}, "structure": {}}

            async def _execute_sync(sess: AsyncSession):
                if not self._mt5:
                    return
                # 1. Fetch & Save OHLCV (M15, H1, H4, D1)
                price_results = await self._mt5.fetch_and_save_all(
                    sess,
                    symbols=target_symbols,
                    timeframes=self.timeframes,
                    count=300,
                )
                summary["price_fetch"] = price_results

                # Publish live TickPriceEvent for each synced symbol to EventBus
                bus = self.event_bus
                if bus is None:
                    try:
                        from utils.protocol.event_bus import get_event_bus
                        bus = get_event_bus()
                    except Exception:
                        bus = None

                if bus and hasattr(self._mt5, "get_current_price"):
                    for sym in target_symbols:
                        try:
                            quote = await self._mt5.get_current_price(sym)
                            if quote and isinstance(quote, dict):
                                bid = float(quote.get("bid", 0.0) or 0.0)
                                ask = float(quote.get("ask", 0.0) or 0.0)
                                last = float(quote.get("last", 0.0) or 0.0)
                                if bid > 0 or ask > 0:
                                    from utils.protocol.event_bus import TickPriceEvent
                                    t_evt = TickPriceEvent(
                                        symbol=sym,
                                        bid=bid,
                                        ask=ask,
                                        last=last or ((bid + ask) / 2.0 if bid and ask else bid or ask),
                                        spread=round(ask - bid, 5) if ask > bid else 0.0,
                                        timestamp=datetime.now(timezone.utc),
                                    )
                                    await bus.publish(t_evt)
                        except Exception as tick_err:
                            logger.debug(f"[MarketDataSync] Failed to publish tick for {sym}: {tick_err}")

                # 2. Compute Technical Indicators (H1, H4, D1)
                indicator_timeframes = [tf for tf in self.timeframes if tf != "M15"]
                calc = TechnicalIndicatorCalculator(sess, self.settings.get("trading", {}))
                ind_results = await calc.compute_all_symbols(target_symbols, indicator_timeframes)
                summary["indicators"] = ind_results

                # 3. Analyze Market Structure (Swings, SR, FVG)
                analyzer = MarketStructureAnalyzer(sess, self.settings)
                struct_results = await analyzer.analyze_all(target_symbols, indicator_timeframes)
                summary["structure"] = {k: sum(v.values()) for k, v in struct_results.items()}

            try:
                if session is not None:
                    await _execute_sync(session)
                else:
                    async with get_session() as sess:
                        await _execute_sync(sess)

                self._last_sync_time = datetime.now(timezone.utc)
                logger.info(
                    f"[MarketDataSync] Sinkronisasi selesai untuk {len(target_symbols)} simbol. "
                    f"Price bars: {sum(summary['price_fetch'].values())} | "
                    f"Indicators: {sum(summary['indicators'].values())} | "
                    f"Structure elements: {sum(summary['structure'].values())}"
                )
                summary["status"] = "success"
                return summary

            except Exception as e:
                logger.error(f"[MarketDataSync] Gagal melakukan sinkronisasi data pasar: {e}")
                summary["status"] = "error"
                summary["error"] = str(e)
                return summary

    async def start(self) -> None:
        """Loop latar belakang untuk sinkronisasi berkala data pasar."""
        self._running = True
        logger.info(f"MarketDataScheduler dimulai (interval: {self.interval_seconds} detik).")

        while self._running:
            try:
                await self.sync_now()
            except Exception as e:
                logger.error(f"Error pada loop MarketDataScheduler: {e}")

            # Jeda sebelum iterasi berikutnya
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        """Menghentikan background scheduler."""
        self._running = False
        self._stop_event.set()
        logger.info("MarketDataScheduler dihentikan.")
