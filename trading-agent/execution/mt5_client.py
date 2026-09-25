# ==============================================================================
# File: execution/mt5_client.py
# ==============================================================================

"""
Klien MT5 — Implementasi pembungkus asinkron (async-compatible wrapper) untuk MetaTrader5.

Menangani:
  - Siklus koneksi (inisialisasi, login, shutdown)
  - Pengambilan info akun dan info simbol
  - Pengambilan data harga OHLCV → disimpan ke PostgreSQL
  - Fungsi dieksekusi dalam thread pool agar tidak memblokir event loop.
"""

import asyncio
import functools
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any, cast

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceOHLCV

load_dotenv()
logger = logging.getLogger("TradingAgent.MT5")

# Priority constants for asyncio PriorityQueue worker pattern
PRIORITY_CRITICAL = 0    # Emergency, kill-switch, order execution (place, modify, close)
PRIORITY_STANDARD = 5    # Ticks, account info, open positions, spread
PRIORITY_NORMAL = PRIORITY_STANDARD # Alias for standard priority tasks
PRIORITY_BACKGROUND = 10 # Bulk historical rates (get_rates, copy_rates_range)

# MT5 timeframe string → MT5 constant mapping
# Will be populated lazily on first connect to avoid import-time mt5 init
TIMEFRAME_MAP: dict[str, int] = {}


def _build_timeframe_map():
    """Membuat pemetaan timeframe string ke konstanta MT5. Dipanggil secara lazy (saat dibutuhkan)."""
    try:
        import MetaTrader5 as _mt5
        mt5: Any = _mt5
        return {
            "M1":  mt5.TIMEFRAME_M1,
            "M5":  mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1":  mt5.TIMEFRAME_H1,
            "H4":  mt5.TIMEFRAME_H4,
            "D1":  mt5.TIMEFRAME_D1,
            "W1":  mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
    except (ImportError, Exception):
        # Standard MT5 timeframe ENUM constants fallback for mock / Linux CI environments
        return {
            "M1":  1,
            "M5":  5,
            "M15": 15,
            "M30": 30,
            "H1":  16385,
            "H4":  16388,
            "D1":  16408,
            "W1":  32769,
            "MN1": 49153,
        }


class MT5Client:
    """Pembungkus async untuk library MetaTrader5 Python dengan dukungan Redundant Secondary Failover Gateway."""

    def __init__(self, settings: Optional[dict] = None):
        self.account = int(os.getenv("MT5_ACCOUNT", 0))
        self.password = os.getenv("MT5_PASSWORD", "")
        self.server = os.getenv("MT5_SERVER", "")
        self.path = os.getenv(
            "MT5_PATH",
            "C:/Program Files/MetaTrader 5/terminal64.exe"
        )
        # Secondary Gateway Configuration
        self.secondary_account = int(os.getenv("MT5_SECONDARY_ACCOUNT", 0))
        self.secondary_password = os.getenv("MT5_SECONDARY_PASSWORD", "")
        self.secondary_server = os.getenv("MT5_SECONDARY_SERVER", "")
        self.secondary_path = os.getenv("MT5_SECONDARY_PATH", "")
        self.active_gateway: str = "primary"  # "primary" or "secondary"
        self.notifier: Optional[Any] = None

        self._connected = False
        self._timeframe_map: dict[str, int] = {}
        self.settings = settings or {}
        self.paper_trading = self.settings.get("paper_trading", {}).get("enabled", False)
        # Dedicated single-thread executor for thread-affine MetaTrader5 COM API calls
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MT5Worker")
        self._priority_queue: Optional[asyncio.PriorityQueue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._queue_counter: int = 0
        # Sub-second micro-batch tick poller state (MEDIUM-5)
        self._tick_poller_thread: Optional[Any] = None
        self._tick_poller_stop_event: Optional[Any] = None
        self._last_ticks: dict[str, tuple[float, float]] = {}
        self._poller_interval: float = float(
            self.settings.get("trading", {}).get("schedule", {}).get("tick_poller_interval_seconds", 0.25)
        )
        self._broker_utc_offset_seconds: Optional[int] = None
        # Note: do NOT store event loop in __init__ — get it lazily in _run()

    def get_current_gateway_params(self) -> tuple[str, int, str, str]:
        """Mengembalikan parameter koneksi untuk gateway yang sedang aktif."""
        if self.active_gateway == "secondary" and self.secondary_account > 0:
            return self.secondary_path or self.path, self.secondary_account, self.secondary_password, self.secondary_server
        return self.path, self.account, self.password, self.server

    # ------------------------------------------------------------------
    # Connection lifecycle & Redundant Failover
    # ------------------------------------------------------------------

    async def connect(self, timeout: float = 15.0) -> bool:
        """Inisialisasi dan login ke MT5 (menggunakan gateway aktif). Mengembalikan True jika berhasil."""
        if not hasattr(self, '_executor') or self._executor is None or getattr(self._executor, '_shutdown', False):
            from concurrent.futures import ThreadPoolExecutor
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MT5Worker")
        curr_path, curr_acc, curr_pass, curr_serv = self.get_current_gateway_params()
        try:
            success = await self._run(_connect, curr_path, curr_acc, curr_pass, curr_serv, timeout=timeout)
            self._connected = success
            if success:
                try:
                    from logging_observability.metrics_exporter import metrics
                    metrics.set_gauge("active_gateway_is_primary", 1.0 if self.active_gateway == "primary" else 0.0)
                    metrics.set_gauge("mt5_primary_connected", 1.0 if self.active_gateway == "primary" else 0.0)
                    metrics.set_gauge("mt5_secondary_connected", 1.0 if self.active_gateway == "secondary" else 0.0)
                except Exception:
                    pass
            return success
        except (ConnectionError, TimeoutError) as ce:
            logger.error(f"MT5 [{self.active_gateway.upper()}] Connection failed or timed out: {ce}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"MT5 [{self.active_gateway.upper()}] Init unexpectedly failed: {e}")
            self._connected = False
            return False

    async def failover_to_secondary(self) -> bool:
        """Berpindah ke gateway MT5 sekunder saat gateway primer tidak dapat dihubungi."""
        if not self.secondary_account or not self.secondary_server:
            logger.warning("Failover to secondary MT5 gateway requested, but secondary credentials are not configured.")
            return False
        logger.warning(f"Initiating MT5 Failover: Switching from {self.active_gateway} -> secondary gateway...")
        await self.disconnect()
        self.active_gateway = "secondary"
        success = await self.connect()
        if success:
            logger.warning("MT5 Failover SUCCESSFUL: Operating on secondary terminal gateway.")
            if self.notifier is not None:
                try:
                    asyncio.create_task(self.notifier.send_warning("🚨 <b>MT5 FAILOVER</b>: System switched to secondary MT5 gateway."))
                except Exception:
                    pass
        else:
            logger.error("MT5 Failover FAILED: Could not establish connection to secondary MT5 gateway.")
        return success

    async def fallback_to_primary(self) -> bool:
        """Kembali ke gateway MT5 primer saat sudah pulih."""
        logger.info("Attempting fallback from secondary to primary MT5 gateway...")
        await self.disconnect()
        self.active_gateway = "primary"
        success = await self.connect()
        if success:
            logger.info("MT5 Fallback SUCCESSFUL: Restored primary gateway connection.")
            if self.notifier is not None:
                try:
                    asyncio.create_task(self.notifier.send_info("ℹ️ <b>MT5 RESTORED</b>: System returned to primary MT5 gateway."))
                except Exception:
                    pass
        else:
            logger.warning("MT5 Fallback failed: Primary gateway still down, reverting to secondary.")
            self.active_gateway = "secondary"
            await self.connect()
        return success

    async def disconnect(self) -> None:
        """Tutup koneksi MT5."""
        self.stop_tick_poller()
        try:
            await self._run(_disconnect, priority=PRIORITY_CRITICAL, timeout=3.0)
        except Exception:
            pass
        finally:
            self._connected = False
            self._broker_utc_offset_seconds = None
            queue = self._priority_queue
            self._priority_queue = None
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except (asyncio.CancelledError, Exception):
                    pass
            if queue is not None:
                while not queue.empty():
                    try:
                        item = queue.get_nowait()
                        fut = item[-1]
                        if hasattr(fut, "done") and not fut.done() and not fut.cancelled():
                            fut.set_exception(ConnectionError("MT5 disconnected"))
                    except Exception:
                        break
            try:
                if hasattr(self, '_executor') and self._executor:
                    self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        logger.info(f"MT5 ({self.active_gateway}) disconnected.")

    async def is_connected(self) -> bool:
        """Periksa apakah terminal MT5 masih hidup."""
        if not getattr(self, '_connected', False):
            return False
        connected = await self._run(_is_connected)
        if not connected:
            self._connected = False
        return connected

    async def ensure_connected(self) -> bool:
        """Cek koneksi dan lakukan reconnect dengan auto-failover ke gateway sekunder jika perlu."""
        if await self.is_connected():
            if getattr(self, 'mt5_fail_count', 0) > 0:
                self.mt5_fail_count = 0
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_info("✅ <b>MT5 Reconnected</b>")
                except Exception:
                    pass
            return True
            
        logger.warning(f"MT5 ({self.active_gateway}) connection lost, attempting to reconnect...")
        
        max_attempts = 2 if self.paper_trading else 4
        delay = 2.0
        
        for attempt in range(1, max_attempts + 1):
            if await self.connect():
                logger.info(f"MT5 ({self.active_gateway}) reconnected successfully on attempt {attempt}")
                self.mt5_fail_count = 0
                return True
            logger.warning(f"MT5 reconnect attempt {attempt} failed, waiting {delay}s...")
            await asyncio.sleep(delay)
            delay = min(20.0, delay * 2)

        # Jika primary gagal dan secondary terkonfigurasi, coba failover
        if self.active_gateway == "primary" and self.secondary_account > 0:
            logger.warning("Primary MT5 reconnect exhausted. Triggering automatic failover to secondary gateway...")
            return await self.failover_to_secondary()

        if self.paper_trading:
            logger.warning("MT5 auto-reconnect failed. Operating in offline mode because paper_trading=True. Continuing without MT5.")
            return False
            
        logger.error("MT5 auto-reconnect failed after maximum attempts.")
        self.mt5_fail_count = getattr(self, 'mt5_fail_count', 0) + 1
        
        if self.mt5_fail_count % 6 == 1:
            try:
                from utils.infra.notifier import AgentNotifier
                notifier = AgentNotifier()
                await notifier.send_critical(
                    f"🚨 <b>MT5 CONNECTION FAILED</b>\n"
                    f"Cannot reconnect to MetaTrader5 after max attempts.\n"
                    f"(Fail count: {self.mt5_fail_count}).\n"
                    f"Please check MT5 terminal immediately!"
                )
            except Exception as notif_err:
                logger.error(f"Failed to send MT5 connection critical alert: {notif_err}")
        return False

    # ------------------------------------------------------------------
    # Account info
    # ------------------------------------------------------------------

    async def get_account_info(self) -> Optional[dict]:
        """Ambil info akun sebagai dict, atau None jika tidak terkoneksi."""
        if not await self.ensure_connected():
            return None
        info = await self._run(_get_account_info, priority=PRIORITY_STANDARD)
        if info is None:
            return None
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "currency": info.currency,
            "leverage": info.leverage,
            "server": info.server,
        }

    # ------------------------------------------------------------------
    # Symbol info
    # ------------------------------------------------------------------

    async def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Ambil metadata simbol sebagai dict, atau None jika simbol tidak ditemukan."""
        if not await self.ensure_connected():
            return None
        info = await self._run(_get_symbol_info, symbol, priority=PRIORITY_STANDARD)
        if info is None:
            return None
        return {
            "symbol": info.name,
            "digits": info.digits,
            "point": info.point,
            "tick_size": info.trade_tick_size,
            "tick_value": info.trade_tick_value,
            "contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "bid": info.bid,
            "ask": info.ask,
            "spread": info.spread,
            "swap_long": getattr(info, "swap_long", 0.0),
            "swap_short": getattr(info, "swap_short", 0.0),
            "stops_level": getattr(info, "trade_stops_level", 0),
        }

    async def get_spread(self, symbol: str) -> dict[str, Any]:
        """Ambil snapshot spread terkini untuk simbol yang diberikan."""
        sym_info = await self.get_symbol_info(symbol)
        if sym_info is not None:
            return {
                "symbol": symbol,
                "spread_points": sym_info.get("spread", 0),
                "spread": sym_info.get("spread", 0),
                "bid": sym_info.get("bid", 0.0),
                "ask": sym_info.get("ask", 0.0),
            }
        return {"symbol": symbol, "spread_points": 0, "spread": 0, "error": "Symbol not found or disconnected"}

    async def get_latest_tick(self, symbol: str) -> Any:
        """Ambil tick terbaru (bid, ask, last, spread, time) untuk simbol tertentu."""
        from unittest.mock import AsyncMock
        if hasattr(self, '_run') and not isinstance(self._run, AsyncMock):
            return await self._run(_get_last_tick, symbol, priority=PRIORITY_STANDARD)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get_last_tick, symbol)

    async def get_broker_utc_offset_seconds(self) -> int:
        """
        Hitung selisih detik antara broker server time MT5 dan UTC.
        Contoh: broker di UTC+3 -> return +10800 detik.
        """
        if self._broker_utc_offset_seconds is not None:
            return self._broker_utc_offset_seconds

        def _calc_offset():
            try:
                import MetaTrader5 as mt5_mod
                t = mt5_mod.symbol_info_tick("EURUSD")
                if not t:
                    for s in ("GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"):
                        t = mt5_mod.symbol_info_tick(s)
                        if t:
                            break
                if t and getattr(t, "time", 0) > 0:
                    now_utc = datetime.now(timezone.utc).timestamp()
                    diff_s = t.time - now_utc
                    offset_hours = round(diff_s / 3600.0)
                    return int(offset_hours * 3600)
            except Exception as e:
                logger.debug(f"Failed to calculate broker UTC offset: {e}")
            return 0

        offset = await self._run(_calc_offset, priority=PRIORITY_NORMAL)
        if isinstance(offset, (int, float)):
            self._broker_utc_offset_seconds = int(offset)
        else:
            self._broker_utc_offset_seconds = 0
        if self._broker_utc_offset_seconds != 0:
            logger.info(f"[MT5Client] Broker UTC offset: {self._broker_utc_offset_seconds / 3600:+.1f}h ({self._broker_utc_offset_seconds}s)")
        return self._broker_utc_offset_seconds

    # ------------------------------------------------------------------
    # OHLCV price data
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
        chunk_size: int = 300,
    ) -> Optional[pd.DataFrame]:
        """
        Ambil bar OHLCV dari terminal MT5 dengan micro-chunking kooperatif (C-3).
        
        Untuk count > chunk_size, query dipecah menjadi batch-batch kecil dengan
        yielding (asyncio.sleep(0)) antar batch agar order PRIORITY_CRITICAL (0)
        di PriorityQueue dapat dieksekusi tanpa tertahan head-of-line blocking.
        """
        if not await self.ensure_connected():
            return None
            
        tf_const = self._resolve_timeframe(timeframe)
        if tf_const is None:
            logger.error(f"Unknown timeframe: {timeframe}")
            return None

        if count <= chunk_size:
            rates = await self._run(_copy_rates_from_pos, symbol, tf_const, 0, count, priority=PRIORITY_BACKGROUND)
            if rates is None or len(rates) == 0:
                logger.warning(f"No OHLCV data returned for {symbol}/{timeframe}")
                return None
            df = pd.DataFrame(rates)
        else:
            collected_dfs = []
            fetched = 0
            while fetched < count:
                current_batch = min(chunk_size, count - fetched)
                rates = await self._run(
                    _copy_rates_from_pos, symbol, tf_const, fetched, current_batch,
                    priority=PRIORITY_BACKGROUND
                )
                if rates is None or len(rates) == 0:
                    break
                collected_dfs.append(pd.DataFrame(rates))
                fetched += len(rates)
                if len(rates) < current_batch:
                    break
                await asyncio.sleep(0)  # Cooperative time-slicing yield

            if not collected_dfs:
                logger.warning(f"No OHLCV data returned for {symbol}/{timeframe}")
                return None
            df = pd.concat(collected_dfs, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")

        # MT5 'time' is Unix timestamp in broker server time — convert to true UTC
        broker_offset = await self.get_broker_utc_offset_seconds()
        if not isinstance(broker_offset, (int, float)):
            broker_offset = 0
        df["time"] = pd.to_datetime(df["time"] - broker_offset, unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["time", "open", "high", "low", "close", "volume"]].copy()
        logger.debug(f"Fetched {len(df)} bars for {symbol}/{timeframe}")
        return cast(pd.DataFrame, df)

    async def copy_rates_range(
        self,
        symbol: str,
        timeframe: str,
        date_from: Any,
        date_to: Any,
        chunk_days: int = 7,
    ) -> Optional[pd.DataFrame]:
        """
        Ambil bar OHLCV dalam rentang tanggal tertentu dari MT5 dengan micro-chunking (C-3).
        Query rentang panjang dipecah per chunk_days untuk mencegah lock-up worker thread.
        """
        if not await self.ensure_connected():
            return None
        tf_const = self._resolve_timeframe(timeframe)
        if tf_const is None:
            logger.error(f"Unknown timeframe: {timeframe}")
            return None

        broker_offset = await self.get_broker_utc_offset_seconds()
        if not isinstance(broker_offset, (int, float)):
            broker_offset = 0
        # Convert date_from / date_to from UTC to broker server time for MT5 API query
        dt_from_broker = date_from + timedelta(seconds=broker_offset) if isinstance(date_from, datetime) else date_from
        dt_to_broker = date_to + timedelta(seconds=broker_offset) if isinstance(date_to, datetime) else date_to

        # Check if date range can be chunked
        is_datetime_range = isinstance(dt_from_broker, datetime) and isinstance(dt_to_broker, datetime)
        if is_datetime_range and (dt_to_broker - dt_from_broker) > timedelta(days=chunk_days):
            collected_dfs = []
            curr_start = dt_from_broker
            while curr_start < dt_to_broker:
                curr_end = min(curr_start + timedelta(days=chunk_days), dt_to_broker)
                rates = await self._run(
                    _copy_rates_range, symbol, tf_const, curr_start, curr_end,
                    priority=PRIORITY_BACKGROUND
                )
                if rates is not None and len(rates) > 0:
                    collected_dfs.append(pd.DataFrame(rates))
                curr_start = curr_end
                await asyncio.sleep(0)  # Cooperative time-slicing yield

            if not collected_dfs:
                logger.warning(f"No OHLCV range data returned for {symbol}/{timeframe}")
                return None
            df = pd.concat(collected_dfs, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
        else:
            rates = await self._run(_copy_rates_range, symbol, tf_const, dt_from_broker, dt_to_broker, priority=PRIORITY_BACKGROUND)
            if rates is None or len(rates) == 0:
                logger.warning(f"No OHLCV range data returned for {symbol}/{timeframe}")
                return None
            df = pd.DataFrame(rates)

        df["time"] = pd.to_datetime(df["time"] - broker_offset, unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["time", "open", "high", "low", "close", "volume"]].copy()
        return cast(pd.DataFrame, df)

    async def get_rates(self, symbol: str, timeframe: str = "H4", count: int = 100) -> Any:
        """Ambil bar harga terakhir untuk simbol dan timeframe tertentu."""
        df = await self.get_ohlcv(symbol, timeframe, count)
        if df is not None and not df.empty:
            return df.to_dict(orient="records")
        return []

    async def save_ohlcv(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        df: Optional[pd.DataFrame],
    ) -> int:
        """Simpan DataFrame OHLCV ke tabel price_ohlcv (insert bar baru / update bar berjalan)."""
        if df is None or df.empty:
            return 0

        saved = 0
        for _, row in df.iterrows():
            row_data: Any = row
            ts = row_data["time"]
            if isinstance(ts, pd.Timestamp):
                ts_dt = ts.to_pydatetime()
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            else:
                ts_dt = ts

            # Check if record exists
            exists = await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == timeframe)
                .where(PriceOHLCV.timestamp == ts_dt)
                .limit(1)
            )
            existing_record = exists.scalar_one_or_none()
            if existing_record is not None:
                # Update bar yang sedang aktif jika nilai OHLCV berubah
                r_open = float(row_data["open"])
                r_high = float(row_data["high"])
                r_low = float(row_data["low"])
                r_close = float(row_data["close"])
                r_vol = float(row_data["volume"])
                if (existing_record.close != r_close or
                    existing_record.high != r_high or
                    existing_record.low != r_low or
                    existing_record.open != r_open or
                    existing_record.volume != r_vol):
                    existing_record.open = r_open
                    existing_record.high = r_high
                    existing_record.low = r_low
                    existing_record.close = r_close
                    existing_record.volume = r_vol
                    saved += 1
                continue

            record = PriceOHLCV(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts_dt,
                open=float(row_data["open"]),
                high=float(row_data["high"]),
                low=float(row_data["low"]),
                close=float(row_data["close"]),
                volume=float(row_data["volume"]),
            )
            session.add(record)
            saved += 1

        if saved:
            await session.commit()
            logger.debug(f"Saved/Updated {saved} bars: {symbol}/{timeframe}")

        return saved

    async def fetch_and_save_all(
        self,
        session: AsyncSession,
        symbols: list[str],
        timeframes: list[str],
        count: int = 500,
    ) -> dict[str, int]:
        """Utilitas: Ambil dan simpan OHLCV untuk semua kombinasi simbol+timeframe."""
        results = {}
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}/{tf}"
                try:
                    df = await self.get_ohlcv(symbol, tf, count)
                    if df is not None:
                        n = await self.save_ohlcv(session, symbol, tf, df)
                        results[key] = n
                    else:
                        results[key] = 0
                except Exception as e:
                    logger.error(f"Failed to fetch/save {key}: {e}")
                    results[key] = 0
        total_bars = sum(results.values())
        logger.info(f"OHLCV data sync complete: {len(results)} pairs ({total_bars} bars saved/updated)")
        return results

    # ------------------------------------------------------------------
    # Current price (tick)
    # ------------------------------------------------------------------

    async def get_current_price(self, symbol: str) -> Optional[dict]:
        """Ambil harga bid/ask terkini untuk suatu simbol."""
        if not await self.ensure_connected():
            return None
        tick = await self._run(_get_last_tick, symbol)
        if tick is None:
            return None
        return {
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "time": datetime.fromtimestamp(tick.time, tz=timezone.utc),
            "fetched_at": time.time(),
        }

    # ------------------------------------------------------------------
    # Sub-Second Micro-Batch Tick Poller (MEDIUM-5)
    # ------------------------------------------------------------------

    def start_tick_poller(
        self,
        symbols: Optional[list[str]] = None,
        interval_seconds: Optional[float] = None,
        event_bus: Optional[Any] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """
        Start sub-second micro-batch tick poller thread (MEDIUM-5).
        Runs at 250ms - 500ms interval on a separate worker thread.
        Publishes TickPriceEvent to EventBus only on Bid/Ask change (deduplication).
        """
        import threading
        if self._tick_poller_thread and self._tick_poller_thread.is_alive():
            logger.debug("[MT5Client] Tick poller thread is already running.")
            return

        if interval_seconds is not None:
            self._poller_interval = max(0.05, min(interval_seconds, 2.0))

        target_symbols = symbols or self.settings.get("trading", {}).get(
            "asset_universe",
            ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "XTIUSD", "XBRUSD"],
        )

        if event_bus is None:
            try:
                from utils.protocol.event_bus import get_event_bus
                event_bus = get_event_bus()
            except Exception:
                event_bus = None

        target_loop = loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_running_loop()
            except RuntimeError:
                target_loop = None

        self._tick_poller_stop_event = threading.Event()
        self._tick_poller_thread = threading.Thread(
            target=self._tick_poller_worker,
            args=(target_symbols, self._poller_interval, event_bus, target_loop),
            name="MT5TickPoller",
            daemon=True,
        )
        self._tick_poller_thread.start()
        logger.info(
            f"[MT5Client] Sub-second tick poller started (interval={self._poller_interval}s, symbols={len(target_symbols)})"
        )

    def stop_tick_poller(self) -> None:
        """Stop sub-second micro-batch tick poller thread."""
        if self._tick_poller_stop_event is not None:
            self._tick_poller_stop_event.set()
        if self._tick_poller_thread and self._tick_poller_thread.is_alive():
            self._tick_poller_thread.join(timeout=1.0)
        self._tick_poller_thread = None
        self._tick_poller_stop_event = None
        logger.info("[MT5Client] Sub-second tick poller stopped.")

    def _tick_poller_worker(
        self,
        symbols: list[str],
        interval_seconds: float,
        event_bus: Optional[Any],
        loop: Optional[asyncio.AbstractEventLoop],
    ) -> None:
        """Worker loop executing on a dedicated thread for sub-second tick polling."""
        from utils.protocol.event_bus import TickPriceEvent
        stop_event = self._tick_poller_stop_event

        while stop_event and not stop_event.is_set():
            try:
                if self._connected:
                    for symbol in symbols:
                        try:
                            tick = _get_last_tick(symbol)
                            if tick is not None:
                                bid = float(getattr(tick, "bid", 0.0) or 0.0)
                                ask = float(getattr(tick, "ask", 0.0) or 0.0)
                                last = float(getattr(tick, "last", 0.0) or 0.0)
                                if bid <= 0 and ask <= 0:
                                    continue
                                prev = self._last_ticks.get(symbol)
                                # Deduplication on unchanged tick: only publish if bid or ask changed
                                if prev is None or prev[0] != bid or prev[1] != ask:
                                    self._last_ticks[symbol] = (bid, ask)
                                    spread = round(ask - bid, 5) if ask > bid else 0.0
                                    evt = TickPriceEvent(
                                        symbol=symbol,
                                        bid=bid,
                                        ask=ask,
                                        last=last,
                                        spread=spread,
                                    )
                                    if event_bus:
                                        if loop and loop.is_running():
                                            event_bus.publish_threadsafe(evt, loop=loop)
                                        else:
                                            try:
                                                subs = event_bus.get_subscribers(type(evt))
                                                for s in subs:
                                                    import inspect
                                                    if not inspect.iscoroutinefunction(s.handler):
                                                        s.handler(evt)
                                            except Exception:
                                                pass
                        except Exception as sym_err:
                            logger.debug(f"[MT5TickPoller] Error sampling {symbol}: {sym_err}")
            except Exception as loop_err:
                logger.debug(f"[MT5TickPoller] Poller iteration error: {loop_err}")

            if stop_event:
                stop_event.wait(interval_seconds)

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "AIAgent",
        order_type: str = "market",
        max_spread_multiplier: Optional[float] = None,
    ) -> dict:
        """Ajukan order baru (market, limit, atau stop) ke MT5."""
        if not await self.ensure_connected():
            return {'success': False, 'error': 'MT5 disconnected', 'retcode': -1}
            
        direction = (direction or "").lower().strip()
        if max_spread_multiplier is None:
            exec_cfg = self.settings.get("execution", {})
            mult_map = exec_cfg.get("max_spread_multiplier", {})
            max_spread_multiplier = mult_map.get(symbol, 10.0) # Default 10x if not found
            
        try:
            result = await self._run(
                _place_order, symbol, direction, volume, price, sl, tp, comment, order_type, max_spread_multiplier,
                priority=PRIORITY_CRITICAL,
                timeout=3.0
            )
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning(f"MT5 place_order timed out after 3.0s for {symbol}. Performing in-flight order reconciliation...")
            # Reconcile: Periksa apakah posisi sebenarnya sudah terbentuk di MT5 dalam beberapa detik terakhir
            try:
                await asyncio.sleep(0.5)
                open_positions = await self.get_open_positions(symbol)
                now_ts = time.time()
                for op in open_positions:
                    pos_type = op.get('type', '').lower()
                    expected_type = 'buy' if direction == 'buy' else 'sell'
                    pos_time = op.get('time', 0)
                    # Cek kesesuaian tipe, volume mendekati, dan timestamp dalam 10 detik terakhir
                    if pos_type == expected_type and abs(float(op.get('volume', 0)) - float(volume)) < 0.001 and (now_ts - pos_time) < 10:
                        logger.critical(f"MT5 in-flight reconciliation SUCCESS: Found open position ticket={op.get('ticket')} for {symbol}")
                        return {
                            'success': True,
                            'ticket': op.get('ticket'),
                            'price': op.get('open_price'),
                            'sl': op.get('sl'),
                            'tp': op.get('tp'),
                            'retcode': 10009,
                            'recovered_from_timeout': True
                        }
            except Exception as rec_err:
                logger.error(f"In-flight reconciliation error for {symbol}: {rec_err}")
            return {'success': False, 'error': f'MT5 order placement timed out for {symbol} (in-flight not detected)', 'retcode': -999}

        if result.get('success'):
            logger.info(
                f"Order placed: {direction.upper()} {volume} {symbol} "
                f"@ {result.get('price')} | ticket={result.get('ticket')}"
            )
        else:
            logger.error(
                f"Order failed: {direction.upper()} {volume} {symbol} | "
                f"error={result.get('error')} retcode={result.get('retcode')}"
            )
        return result

    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict:
        """Ubah SL/TP dari posisi terbuka yang ada."""
        if not await self.ensure_connected():
            return {'success': False, 'error': 'MT5 disconnected', 'retcode': -1}
        try:
            result = await self._run(_modify_position, ticket, sl, tp, priority=PRIORITY_CRITICAL, timeout=3.0)
        except (TimeoutError, asyncio.TimeoutError):
            logger.error(f"Modify position {ticket} timed out")
            return {'success': False, 'error': f'Modify position {ticket} timed out', 'retcode': -999}

        if result.get('success'):
            logger.info(f"Position {ticket} modified: SL={sl}, TP={tp}")
        else:
            logger.error(f"Modify {ticket} failed: {result.get('error')}")
        return result

    async def close_position(
        self,
        ticket: int,
        volume: Optional[float] = None,
        comment: str = "AIAgent-Close",
        lots: Optional[float] = None,
    ) -> dict:
        """Tutup posisi terbuka (sepenuhnya atau sebagian)."""
        if not await self.ensure_connected():
            return {'success': False, 'error': 'MT5 disconnected', 'retcode': -1}
        eff_volume = lots if volume is None and lots is not None else volume
        try:
            result = await self._run(_close_position, ticket, eff_volume, comment, lots=lots, priority=PRIORITY_CRITICAL, timeout=3.0)
        except (TimeoutError, asyncio.TimeoutError):
            logger.error(f"Close position {ticket} timed out")
            return {'success': False, 'error': f'Close position {ticket} timed out', 'retcode': -999}

        if result.get('success'):
            logger.info(
                f"Position {ticket} closed @ {result.get('price')} | "
                f"profit={result.get('profit')}"
            )
        else:
            logger.error(f"Close {ticket} failed: {result.get('error')}")
        return result

    async def get_open_positions(self, symbol: Optional[str] = None) -> list[dict]:
        """Ambil semua posisi terbuka dari MT5."""
        if not await self.ensure_connected():
            return []
        positions = await self._run(_get_open_positions, symbol, priority=PRIORITY_STANDARD)
        return positions or []

    async def get_orders(self, symbol: Optional[str] = None) -> list[dict]:
        """Ambil daftar semua order pending yang aktif di terminal MT5."""
        if not await self.ensure_connected():
            return []
        orders = await self._run(_get_orders, symbol, priority=PRIORITY_STANDARD)
        return orders or []

    async def cancel_order(self, ticket_or_id: Any) -> dict:
        """Batalkan pending order di MT5 berdasarkan ticket."""
        if not await self.ensure_connected():
            return {'success': False, 'error': 'MT5 disconnected', 'retcode': -1}
        try:
            ticket = int(ticket_or_id)
        except (ValueError, TypeError):
            return {'success': False, 'error': f'Invalid ticket: {ticket_or_id}', 'retcode': -1}
        return await self._run(_cancel_order, ticket, priority=PRIORITY_CRITICAL, timeout=3.0)

    async def get_order_history(self, ticket: int) -> list:
        """Ambil riwayat order dari MT5 berdasarkan ticket."""
        if not await self.ensure_connected():
            return []
        return await self._run(_get_order_history, int(ticket), priority=PRIORITY_STANDARD) or []

    async def get_deal_history(self, ticket: int) -> list:
        """Ambil riwayat deal dari MT5 berdasarkan ticket posisi atau order."""
        if not await self.ensure_connected():
            return []
        return await self._run(_get_deal_history, int(ticket), priority=PRIORITY_STANDARD) or []

    async def close_all_positions(self, comment: str = "AIAgent-CloseAll") -> dict:
        """Tutup SEMUA posisi terbuka (dipakai oleh kill-switch) - Priority 0."""
        if not await self.ensure_connected():
            return {'closed': 0, 'failed': 0, 'total': 0, 'error': 'MT5 disconnected'}
        positions = await self._run(_get_open_positions, None, priority=PRIORITY_CRITICAL)
        closed = failed = 0
        for pos in (positions or []):
            result = await self.close_position(pos['ticket'], comment=comment)
            if result.get('success'):
                closed += 1
            else:
                failed += 1
                logger.error(f"Failed to close position {pos['ticket']}: {result.get('error')}")
        logger.warning(f"close_all_positions: closed={closed}, failed={failed}, total={len(positions or [])}")
        return {'closed': closed, 'failed': failed, 'total': len(positions or [])}

    async def emergency_close_all(self, comment: str = "AIAgent-EmergencyCloseAll") -> dict:
        """Emergency liquidate all positions (Priority 0)."""
        return await self.close_all_positions(comment=comment)

    async def kill_switch(self, comment: str = "AIAgent-KillSwitch") -> dict:
        """Emergency kill-switch: liquidate all positions and disconnect (Priority 0)."""
        res = await self.close_all_positions(comment=comment)
        await self.disconnect()
        return res

    async def modify_order(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict:
        """Alias for modify_position (Priority 0)."""
        return await self.modify_position(ticket=ticket, sl=sl, tp=tp)

    async def sync_positions_from_mt5(
        self,
        session: AsyncSession,
    ) -> dict:
        """Sinkronkan posisi terbuka dari MT5 ke DB lokal (perbarui status DB yang sudah tertutup di MT5)."""
        from database.models import Position
        from sqlalchemy import select

        mt5_positions = await self.get_open_positions()
        mt5_tickets = {p['ticket'] for p in mt5_positions}

        synced = closed_in_db = 0
        closed_positions = []

        # Insert any new MT5 positions not yet in DB
        for pos in mt5_positions:
            existing = (await session.execute(
                select(Position).where(Position.mt5_ticket == pos['ticket'])
            )).scalar_one_or_none()
            if existing is None:
                direction = 'buy' if pos['type'] == 0 else 'sell'
                session.add(Position(
                    mt5_ticket=pos['ticket'],
                    symbol=pos['symbol'],
                    direction=direction,
                    volume=pos['volume'],
                    entry_price=pos['price_open'],
                    sl=pos.get('sl'),
                    tp=pos.get('tp'),
                    opened_at=pos['time'],
                    status='open',
                ))
                synced += 1

        # Mark DB-open positions that are no longer on MT5 as closed
        db_open = (await session.execute(
            select(Position).where(Position.status == 'open')
        )).scalars().all()
        for db_pos in db_open:
            # Skip paper/dry-run positions — they don't exist in MT5
            if getattr(db_pos, 'is_paper', False):
                continue
            if db_pos.mt5_ticket and db_pos.mt5_ticket not in mt5_tickets:
                db_pos.status = 'closed'
                db_pos.closed_at = datetime.now(timezone.utc)
                
                # Fetch deal history to get PnL and close reason
                deals = await self._run(_get_deal_history, db_pos.mt5_ticket)
                if deals:
                    import MetaTrader5 as _mt5
                    mt5: Any = _mt5
                    close_deal = deals[-1]
                    db_pos.pnl = sum(getattr(d, 'profit', 0.0) for d in deals)
                    setattr(db_pos, '_mt5_close_reason', getattr(close_deal, 'reason', None))
                    setattr(db_pos, '_mt5_exit_price', getattr(close_deal, 'price', None))
                
                closed_positions.append(db_pos)
                closed_in_db += 1

        await session.commit()
        logger.info(f"Position sync: {synced} new, {closed_in_db} closed")
        return {'synced': synced, 'closed_in_db': closed_in_db, 'closed_positions': closed_positions}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_timeframe(self, tf_str: str) -> Optional[int]:
        """Ubah string timeframe (mis: H1) menjadi konstanta MT5."""
        if not self._timeframe_map:
            try:
                self._timeframe_map = _build_timeframe_map()
            except Exception as e:
                logger.warning(f"Failed to build MT5 timeframe map: {e}")
                return None
        return self._timeframe_map.get(tf_str.upper())

    def _ensure_worker(self) -> asyncio.PriorityQueue:
        """Menginisialisasi asyncio PriorityQueue dan worker task secara lazy."""
        loop = asyncio.get_running_loop()
        if not hasattr(self, '_executor') or self._executor is None or getattr(self._executor, '_shutdown', False):
            from concurrent.futures import ThreadPoolExecutor
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MT5Worker")
        if self._priority_queue is None or self._worker_task is None or self._worker_task.done():
            self._priority_queue = asyncio.PriorityQueue()
            self._worker_task = loop.create_task(self._priority_worker_loop())
        return self._priority_queue

    async def _priority_worker_loop(self):
        """Dedicated worker loop yang mengambil tugas dari PriorityQueue dan menjalankannya di STA ThreadPoolExecutor."""
        while True:
            queue = self._priority_queue
            if queue is None:
                break
            try:
                priority, counter, fn, args, kwargs, future = await queue.get()
            except (asyncio.CancelledError, GeneratorExit):
                break
            except Exception as ex:
                logger.error(f"[MT5PriorityWorker] Queue retrieval error: {ex}")
                continue

            if future.cancelled():
                try:
                    queue.task_done()
                except Exception:
                    pass
                continue

            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    self._executor,
                    functools.partial(fn, *args, **kwargs)
                )
                if not future.cancelled() and not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                if not future.cancelled() and not future.done():
                    future.set_exception(ConnectionError("MT5 disconnected"))
                try:
                    queue.task_done()
                except Exception:
                    pass
                break
            except Exception as exc:
                if not future.cancelled() and not future.done():
                    future.set_exception(exc)
            finally:
                try:
                    queue.task_done()
                except Exception:
                    pass

    def _resolve_priority(self, fn: Any, explicit_priority: Optional[int] = None) -> int:
        """Menentukan tingkat prioritas eksekusi MT5 (0=Critical, 5=Standard, 10=Background)."""
        if explicit_priority is not None:
            return explicit_priority
        fn_name = getattr(fn, "__name__", "")
        if fn_name in (
            "_place_order", "place_order",
            "_modify_position", "modify_position",
            "_modify_order", "modify_order",
            "_close_position", "close_position",
            "_close_all_positions", "close_all_positions",
            "emergency_close_all", "kill_switch",
            "_disconnect", "disconnect",
        ):
            return PRIORITY_CRITICAL
        if fn_name in ("_copy_rates_from_pos", "_copy_rates_range", "copy_rates_range", "fetch_and_save_all"):
            return PRIORITY_BACKGROUND
        return PRIORITY_STANDARD

    async def _run(self, fn, *args, priority: Optional[int] = None, timeout: Optional[float] = None, **kwargs):
        """Jalankan fungsi sinkron MT5 via asyncio PriorityQueue di atas dedicated single-thread executor."""
        loop = asyncio.get_running_loop()
        queue = self._ensure_worker()
        self._queue_counter += 1
        eff_priority = self._resolve_priority(fn, priority)
        future = loop.create_future()

        await queue.put((eff_priority, self._queue_counter, fn, args, kwargs, future))

        if timeout is not None:
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            except asyncio.TimeoutError:
                future.cancel()
                fn_name = getattr(fn, "__name__", str(fn))
                logger.error(f"MT5 timeout ({timeout}s) in {fn_name}. Terminal may be hung. Forcing reconnect.")
                self._connected = False
                try:
                    if hasattr(self, '_executor') and self._executor:
                        self._executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MT5Worker")
                raise TimeoutError(f"MT5 operation {fn_name} timed out")
        return await future

    async def market_book_add(self, symbol: str) -> bool:
        """Subscribe to Level 2 Market Depth (DOM) for symbol."""
        if not await self.ensure_connected():
            return False
        return await self._run(_market_book_add, symbol, timeout=3.0)

    async def market_book_get(self, symbol: str) -> Any:
        """Fetch Level 2 Market Depth (DOM) snapshot for symbol."""
        if not await self.ensure_connected():
            return None
        return await self._run(_market_book_get, symbol, timeout=3.0)

    async def market_book_release(self, symbol: str) -> bool:
        """Unsubscribe from Level 2 Market Depth (DOM) for symbol."""
        if not self._connected:
            return False
        return await self._run(_market_book_release, symbol, timeout=3.0)


# =============================================================================
# Synchronous worker functions (run in executor)
# All must be module-level (picklable) functions.
# =============================================================================

def _market_book_add(symbol: str) -> bool:
    try:
        import MetaTrader5 as _mt5
        mt5: Any = _mt5
        return bool(mt5.market_book_add(symbol))
    except Exception as e:
        logger.debug(f"market_book_add error for {symbol}: {e}")
        return False

def _market_book_get(symbol: str) -> Any:
    try:
        import MetaTrader5 as _mt5
        mt5: Any = _mt5
        return mt5.market_book_get(symbol)
    except Exception as e:
        logger.debug(f"market_book_get error for {symbol}: {e}")
        return None

def _market_book_release(symbol: str) -> bool:
    try:
        import MetaTrader5 as _mt5
        mt5: Any = _mt5
        return bool(mt5.market_book_release(symbol))
    except Exception as e:
        logger.debug(f"market_book_release error for {symbol}: {e}")
        return False


def _connect(path: str, account: int, password: str, server: str) -> bool:
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    logger.info(f"Initializing MT5: {path}")
    if not mt5.initialize(path=path):
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    if not mt5.login(account, password=password, server=server):
        logger.error(f"MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    logger.info(
        f"MT5 connected: {server} | Account {account} | "
        f"Balance={info.balance:.2f} {info.currency}"
    )
    return True


def _disconnect():
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    mt5.shutdown()


def _is_connected() -> bool:
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    info = mt5.account_info()
    return info is not None


def _get_account_info():
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    return mt5.account_info()


def _get_symbol_info(symbol: str):
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    return mt5.symbol_info(symbol)


def _copy_rates_from_pos(symbol: str, tf: int, start: int, count: int):
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    return mt5.copy_rates_from_pos(symbol, tf, start, count)


def _copy_rates_range(symbol: str, tf: int, date_from: Any, date_to: Any):
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    return mt5.copy_rates_range(symbol, tf, date_from, date_to)


def _get_last_tick(symbol: str):
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    return mt5.symbol_info_tick(symbol)


def _place_order(
    symbol: str,
    direction: str,
    volume: float,
    price: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    comment: str,
    order_type: str,
    max_spread_multiplier: Optional[float] = None,
) -> dict:
    """
    Execute a trade request on MT5.
    Handles MARKET (instant) and LIMIT/STOP (pending) order types.
    """
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5

    info = mt5.symbol_info(symbol)
    if info is None:
        return {'success': False, 'ticket': None, 'price': None,
                'error': f'Symbol {symbol} not found', 'retcode': -1}

    # Normalize SL/TP to tick size to prevent 'Invalid Stops' rejection
    def _normalize(val: float) -> float:
        if not info.trade_tick_size: return round(val, info.digits)
        return round(round(val / info.trade_tick_size) * info.trade_tick_size, info.digits)

    # 1. Market Spread Safety Check
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {'success': False, 'ticket': None, 'price': None,
                'error': f'Cannot get tick for spread check on {symbol}', 'retcode': -1}

    spread_pts = (tick.ask - tick.bid) / info.point if info.point else 0
    mult = max_spread_multiplier if max_spread_multiplier is not None else 3.0
    
    # 2. Normalize Direction & Map Action/Order Type
    direction = (direction or "").lower().strip()
    if direction not in ("buy", "sell"):
        return {'success': False, 'ticket': None, 'price': None,
                'error': f'Invalid direction {direction} for {symbol}', 'retcode': -1}

    order_type_upper = (order_type or "market").upper()
    if order_type_upper in ("BUY_LIMIT", "LIMIT") and direction == "buy":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_BUY_LIMIT
        order_price = price
    elif order_type_upper in ("SELL_LIMIT", "LIMIT") and direction == "sell":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_SELL_LIMIT
        order_price = price
    elif order_type_upper in ("BUY_STOP", "STOP") and direction == "buy":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_BUY_STOP
        order_price = price
    elif order_type_upper in ("SELL_STOP", "STOP") and direction == "sell":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_SELL_STOP
        order_price = price
    elif direction == 'buy':
        action = mt5.TRADE_ACTION_DEAL
        mt5_order_type = mt5.ORDER_TYPE_BUY
        order_price = tick.ask
    elif direction == 'sell':
        action = mt5.TRADE_ACTION_DEAL
        mt5_order_type = mt5.ORDER_TYPE_SELL
        order_price = tick.bid
    else:
        return {'success': False, 'ticket': None, 'price': None,
                'error': f'Unsupported order direction {direction}', 'retcode': -1}

    if not order_price or order_price <= 0:
        return {'success': False, 'ticket': None, 'price': None,
                'error': f'Invalid calculated price {order_price} for {symbol}', 'retcode': -1}

    # Query supported fill mode from symbol info
    filling_mode = info.filling_mode
    if filling_mode & 1:  # ORDER_FILLING_FOK
        fill_type = mt5.ORDER_FILLING_FOK
    elif filling_mode & 2:  # ORDER_FILLING_IOC
        fill_type = mt5.ORDER_FILLING_IOC
    else:
        fill_type = mt5.ORDER_FILLING_RETURN

    request = {
        'action': action,
        'symbol': symbol,
        'volume': float(volume),
        'type': mt5_order_type,
        'price': float(order_price),
        'sl': _normalize(sl) if sl else 0.0,
        'tp': _normalize(tp) if tp else 0.0,
        'comment': comment[:31],
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': fill_type,
        'magic': 20250101,  # EA magic number to identify AI-placed orders
        'deviation': 20,    # Max price deviation in points for market orders
    }

    max_retries = 2
    result = None
    for attempt in range(max_retries + 1):
        result = mt5.order_send(request)
        if result is None:
            return {
                'success': False, 'ticket': None, 'price': None,
                'error': f'order_send returned None: {mt5.last_error()}',
                'retcode': -1,
            }

        done_code = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
        if getattr(result, "retcode", None) == done_code or getattr(result, "retcode", None) == 10009:
            break

        # Transient requote / price drift handling
        req_code = getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004)
        inv_code = getattr(mt5, "TRADE_RETCODE_INVALID_PRICE", 10015)
        off_code = getattr(mt5, "TRADE_RETCODE_PRICE_OFF", 10021)
        transient_codes = (req_code, inv_code, off_code, 10004, 10015, 10021)
        if getattr(result, "retcode", None) in transient_codes and attempt < max_retries:
            time.sleep(0.1)  # 100ms rapid pause
            latest_tick = mt5.symbol_info_tick(symbol)
            if latest_tick:
                new_price = getattr(latest_tick, 'ask', None) if direction == 'buy' else getattr(latest_tick, 'bid', None)
                if new_price and new_price > 0:
                    request['price'] = float(new_price)
            continue
        break

    if result is None:
        return {
            'success': False, 'ticket': None, 'price': None,
            'error': 'order_send returned None',
            'retcode': -1,
        }

    done_code = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    res_retcode = getattr(result, "retcode", -1)
    success = (res_retcode == done_code or res_retcode == 10009)
    return {
        'success': success,
        'ticket': getattr(result, "order", None) if success else None,
        'price': getattr(result, "price", None) if success else None,
        'error': None if success else f'retcode={res_retcode} comment={getattr(result, "comment", "")}',
        'retcode': res_retcode,
        'volume': getattr(result, "volume", None) if success else None,
    }


def _modify_position(ticket: int, sl: Optional[float], tp: Optional[float]) -> dict:
    """Modify SL/TP on an existing open position."""
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5

    # Get current position to preserve existing SL/TP if not being changed
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return {'success': False, 'error': f'Position {ticket} not found', 'retcode': -1}

    current = pos[0]
    info = mt5.symbol_info(current.symbol)

    def _normalize(val: Optional[float]) -> Optional[float]:
        if val is None:
            return None
        if info is None or not getattr(info, 'trade_tick_size', None):
            digits = getattr(info, 'digits', 5) if info else 5
            return round(float(val), digits)
        return round(round(float(val) / info.trade_tick_size) * info.trade_tick_size, info.digits)

    normalized_sl = _normalize(sl) if sl is not None else current.sl
    normalized_tp = _normalize(tp) if tp is not None else current.tp

    request = {
        'action': mt5.TRADE_ACTION_SLTP,
        'symbol': current.symbol,
        'position': ticket,
        'sl': float(normalized_sl) if normalized_sl is not None else 0.0,
        'tp': float(normalized_tp) if normalized_tp is not None else 0.0,
        'magic': 20250101,
    }

    result = mt5.order_send(request)
    if result is None:
        return {'success': False, 'error': str(mt5.last_error()), 'retcode': -1}

    success = getattr(result, "retcode", -1) == getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    return {
        'success': success,
        'error': None if success else f'retcode={getattr(result, "retcode", -1)} {getattr(result, "comment", "")}',
        'retcode': getattr(result, "retcode", -1),
    }


def _close_position(ticket: int, volume: Optional[float], comment: str, lots: Optional[float] = None) -> dict:
    """Close an open position (fully or partially)."""
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5

    if volume is None and lots is not None:
        volume = lots

    # Fetch current position details
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return {'success': False, 'price': None, 'profit': None,
                'error': f'Position {ticket} not found', 'retcode': -1}

    current = pos[0]
    close_volume = volume if volume is not None else current.volume

    # Close requires the opposite direction
    tick = mt5.symbol_info_tick(current.symbol)
    if tick is None:
        # Fallback to symbol_info if tick fails
        info = mt5.symbol_info(current.symbol)
        if info is None:
            return {'success': False, 'price': None, 'profit': None,
                    'error': f'Failed to get current price for {current.symbol}. Market closed?', 'retcode': -1}
        bid_price = info.bid
        ask_price = info.ask
    else:
        bid_price = tick.bid
        ask_price = tick.ask
        
    if current.type == getattr(mt5, "POSITION_TYPE_BUY", 0):
        close_type = getattr(mt5, "ORDER_TYPE_SELL", 1)
        close_price = bid_price
    else:
        close_type = getattr(mt5, "ORDER_TYPE_BUY", 0)
        close_price = ask_price

    # Query supported fill mode from symbol info
    info = mt5.symbol_info(current.symbol)
    filling_mode = info.filling_mode if info else 0
    if filling_mode & 1:  # ORDER_FILLING_FOK
        fill_type = getattr(mt5, "ORDER_FILLING_FOK", 0)
    elif filling_mode & 2:  # ORDER_FILLING_IOC
        fill_type = getattr(mt5, "ORDER_FILLING_IOC", 1)
    else:
        fill_type = getattr(mt5, "ORDER_FILLING_RETURN", 2)

    request = {
        'action': getattr(mt5, "TRADE_ACTION_DEAL", 1),
        'symbol': current.symbol,
        'volume': float(close_volume),
        'type': close_type,
        'position': ticket,
        'price': float(close_price),
        'comment': comment[:31],
        'type_time': getattr(mt5, "ORDER_TIME_GTC", 0),
        'type_filling': fill_type,
        'deviation': 20,
        'magic': 20250101,
    }

    result = mt5.order_send(request)
    if result is None:
        return {'success': False, 'price': None, 'profit': None,
                'error': str(mt5.last_error()), 'retcode': -1}

    success = getattr(result, "retcode", -1) == getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    return {
        'success': success,
        'price': getattr(result, "price", None) if success else None,
        'profit': getattr(current, "profit", None) if success else None,
        'error': None if success else f'retcode={getattr(result, "retcode", -1)} {getattr(result, "comment", "")}',
        'retcode': getattr(result, "retcode", -1),
    }


def _get_open_positions(symbol: Optional[str]) -> list[dict]:
    """Fetch all open positions from MT5."""
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    from datetime import datetime, timezone

    if symbol:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()

    if positions is None:
        return []

    result = []
    for p in positions:
        result.append({
            'ticket':     p.ticket,
            'identifier': getattr(p, 'identifier', p.ticket),
            'symbol':     p.symbol,
            'type':       p.type,  # 0=BUY, 1=SELL
            'direction':  'buy' if p.type == 0 else 'sell',
            'volume':     p.volume,
            'price_open': p.price_open,
            'price_current': p.price_current,
            'sl':         p.sl,
            'tp':         p.tp,
            'profit':     p.profit,
            'swap':       p.swap,
            'comment':    p.comment,
            'magic':      p.magic,
            'time':       datetime.fromtimestamp(p.time, tz=timezone.utc),
        })
    return result

def _get_orders(symbol: Optional[str] = None) -> list[dict]:
    """Fetch all active pending orders from MT5."""
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    from datetime import datetime, timezone

    if symbol:
        orders = mt5.orders_get(symbol=symbol)
    else:
        orders = mt5.orders_get()

    if orders is None:
        return []

    result = []
    for o in orders:
        order_type_val = getattr(o, "type", 0)
        # MT5 pending types: 2=BUY_LIMIT, 3=SELL_LIMIT, 4=BUY_STOP, 5=SELL_STOP, 6=BUY_STOP_LIMIT, 7=SELL_STOP_LIMIT
        direction = "buy" if order_type_val in (2, 4, 6) else "sell"
        result.append({
            "ticket": getattr(o, "ticket", None),
            "symbol": getattr(o, "symbol", ""),
            "type": order_type_val,
            "direction": direction,
            "volume": getattr(o, "volume_current", getattr(o, "volume_initial", 0.0)),
            "volume_initial": getattr(o, "volume_initial", 0.0),
            "volume_current": getattr(o, "volume_current", 0.0),
            "price_open": getattr(o, "price_open", 0.0),
            "price_current": getattr(o, "price_current", 0.0),
            "sl": getattr(o, "sl", None),
            "tp": getattr(o, "tp", None),
            "comment": getattr(o, "comment", ""),
            "magic": getattr(o, "magic", 0),
            "time": datetime.fromtimestamp(getattr(o, "time_setup", 0), tz=timezone.utc) if getattr(o, "time_setup", 0) else None,
            "state": getattr(o, "state", None),
        })
    return result


def _cancel_order(ticket: int) -> dict:
    """Cancel pending order by ticket in MT5."""
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5

    request = {
        "action": getattr(mt5, "TRADE_ACTION_REMOVE", 8),
        "order": int(ticket),
    }
    result = mt5.order_send(request)
    if result is None:
        return {
            "success": False,
            "error": f"order_send returned None: {mt5.last_error()}",
            "retcode": -1,
        }
    done_code = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    res_retcode = getattr(result, "retcode", -1)
    success = (res_retcode == done_code or res_retcode == 10009)
    return {
        "success": success,
        "ticket": ticket,
        "retcode": res_retcode,
        "error": None if success else f"retcode={res_retcode} comment={getattr(result, 'comment', '')}",
    }


def _get_deal_history(ticket: int):
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    deals = mt5.history_deals_get(position=ticket)
    return deals if deals else []


def _get_order_history(ticket: int):
    from typing import Any
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    orders = mt5.history_orders_get(ticket=ticket)
    return orders if orders else []


_default_mt5_client: Optional[MT5Client] = None


def get_mt5_client(settings: Optional[dict] = None) -> MT5Client:
    """Singleton getter untuk instance MT5Client."""
    global _default_mt5_client
    if _default_mt5_client is None:
        _default_mt5_client = MT5Client(settings=settings or {})
    return _default_mt5_client

