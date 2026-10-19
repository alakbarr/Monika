"""
Market data, ticks, OHLCV ingestion, DOM VWAP, and tick polling logic for MT5Client.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import time
from typing import Any, Optional, cast

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import PriceOHLCV

from .base import MT5MixinBase
from .constants import (
    PRIORITY_BACKGROUND,
    PRIORITY_NORMAL,
    PRIORITY_STANDARD,
    _build_timeframe_map,
    logger,
)
from .primitives import (
    _calculate_dom_vwap,
    _copy_rates_from_pos,
    _copy_rates_range,
    _copy_ticks_range,
    _get_account_info,
    _get_last_tick,
    _get_symbol_info,
    _market_book_add,
    _market_book_get,
    _market_book_release,
)


class MT5MarketDataMixin(MT5MixinBase):
    """Mixin providing market quotes, rates caching, DOM book depth, and tick poller."""

    async def get_account_info(self) -> Optional[dict[str, Any]]:
        """Ambil info akun sebagai dict, atau None jika tidak terkoneksi."""
        if not await self.ensure_connected():
            return None
        info = await self._run(_get_account_info, priority=PRIORITY_STANDARD)
        if info is None:
            return None
        curr_str = str(getattr(info, "currency", "")).upper()
        server_str = str(getattr(info, "server", "")).lower()
        cfg_cent = False
        if hasattr(self, "settings") and isinstance(self.settings, dict):
            cfg_cent = bool(self.settings.get("trading", {}).get("risk", {}).get("is_cent_account", False))
        is_cent = cfg_cent or (curr_str in ("USC", "EUCC", "GBPC", "CENT", "GLD")) or ("cent" in server_str)
        norm_factor = 100.0 if is_cent else 1.0

        margin_mode_raw = getattr(info, "margin_mode", 2)
        margin_mode_str = "hedging" if margin_mode_raw == 2 else ("netting" if margin_mode_raw in (0, 1) else "hedging")

        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "currency": info.currency,
            "leverage": info.leverage,
            "margin_mode": margin_mode_str,
            "allow_hedging": (margin_mode_str == "hedging"),
            "server": info.server,
            "trade_mode": getattr(info, "trade_mode", 0),
            "is_demo": getattr(info, "trade_mode", 0) == 0,
            "is_cent_account": is_cent,
            "normalized_balance": float(info.balance) / norm_factor,
            "normalized_equity": float(info.equity) / norm_factor,
        }

    async def get_symbol_info(self, symbol: str) -> Optional[dict[str, Any]]:
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

        if not await self.ensure_connected():
            return None

        if hasattr(self, "_run") and not isinstance(self._run, AsyncMock):
            return await self._run(_get_last_tick, symbol, priority=PRIORITY_STANDARD)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get_last_tick, symbol)

    async def copy_ticks_range(
        self,
        symbol: str,
        date_from: datetime,
        date_to: datetime,
        flags: int = 1,
    ) -> list[dict[str, Any]]:
        """Ambil array ticks historis dalam rentang waktu tertentu dari MT5."""
        if not await self.ensure_connected():
            return []
        from unittest.mock import AsyncMock

        if hasattr(self, "_run") and not isinstance(self._run, AsyncMock):
            return await self._run(_copy_ticks_range, symbol, date_from, date_to, flags, priority=PRIORITY_STANDARD)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _copy_ticks_range, symbol, date_from, date_to, flags)

    async def get_broker_utc_offset_seconds(self) -> int:
        """
        Hitung selisih detik antara broker server time MT5 dan UTC.
        Contoh: broker di UTC+3 -> return +10800 detik.
        """
        if self._broker_utc_offset_seconds is not None:
            return self._broker_utc_offset_seconds

        # 1. Konfigurasi eksplisit dari settings jika tersedia
        mt5_cfg = self.settings.get("trading", {}).get("mt5", {})
        cfg_offset = mt5_cfg.get("broker_utc_offset_hours")
        if cfg_offset is not None:
            try:
                self._broker_utc_offset_seconds = int(float(cfg_offset) * 3600)
                logger.info(
                    f"[MT5Client] Broker UTC offset configured: {float(cfg_offset):+.1f}h ({self._broker_utc_offset_seconds}s)"
                )
                return self._broker_utc_offset_seconds
            except Exception as e:
                logger.warning(f"[MT5Client] Invalid broker_utc_offset_hours in settings: {e}")

        def _calc_offset() -> int:
            try:
                import MetaTrader5 as mt5_mod

                now_utc = datetime.now(timezone.utc).timestamp()
                # Prioritaskan simbol yang aktif berdetak (24/7 crypto), lalu forex mayor
                symbols_to_check = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
                for s in symbols_to_check:
                    t = mt5_mod.symbol_info_tick(s)
                    if t and getattr(t, "time", 0) > 0:
                        diff_s = t.time - now_utc
                        offset_hours = round(diff_s / 3600.0)
                        residual_s = abs(diff_s - (offset_hours * 3600))
                        # Abaikan tick yang kadaluarsa (>30 menit) karena pasar tutup (cth: EURUSD di weekend)
                        if residual_s < 1800 and -14 <= offset_hours <= 14:
                            return int(offset_hours * 3600)
            except Exception as e:
                logger.debug(f"Failed to calculate broker UTC offset: {e}")
            return 0

        offset = await self._run(_calc_offset, priority=PRIORITY_NORMAL)
        if isinstance(offset, (int, float)) and -14 * 3600 <= int(offset) <= 14 * 3600:
            self._broker_utc_offset_seconds = int(offset)
        else:
            self._broker_utc_offset_seconds = 0
        if self._broker_utc_offset_seconds != 0:
            logger.info(
                f"[MT5Client] Broker UTC offset auto-detected: {self._broker_utc_offset_seconds / 3600:+.1f}h ({self._broker_utc_offset_seconds}s)"
            )
        return self._broker_utc_offset_seconds

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
                    _copy_rates_from_pos, symbol, tf_const, fetched, current_batch, priority=PRIORITY_BACKGROUND
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
                    _copy_rates_range, symbol, tf_const, curr_start, curr_end, priority=PRIORITY_BACKGROUND
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
            rates = await self._run(
                _copy_rates_range, symbol, tf_const, dt_from_broker, dt_to_broker, priority=PRIORITY_BACKGROUND
            )
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
            if existing_record is None and timeframe == "D1":
                # Fallback: cek apakah bar D1 pada jendela hari yang sama (+-6 jam) sudah ada
                near_exists = await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == timeframe)
                    .where(PriceOHLCV.timestamp >= ts_dt - timedelta(hours=6))
                    .where(PriceOHLCV.timestamp <= ts_dt + timedelta(hours=6))
                    .limit(1)
                )
                existing_record = near_exists.scalar_one_or_none()
                if existing_record is not None:
                    existing_record.timestamp = ts_dt
            if existing_record is not None:
                # Update bar yang sedang aktif jika nilai OHLCV berubah
                r_open = float(row_data["open"])
                r_high = float(row_data["high"])
                r_low = float(row_data["low"])
                r_close = float(row_data["close"])
                r_vol = float(row_data["volume"])
                if (
                    existing_record.close != r_close
                    or existing_record.high != r_high
                    or existing_record.low != r_low
                    or existing_record.open != r_open
                    or existing_record.volume != r_vol
                ):
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
            from monika.infrastructure.database.safe_ops import safe_commit

            ok = await safe_commit(session, label=f"ohlcv_{symbol}_{timeframe}")
            if ok:
                logger.debug(f"Saved/Updated {saved} bars: {symbol}/{timeframe}")
            else:
                return 0

        return saved

    async def fetch_and_save_all(
        self,
        session: AsyncSession,
        symbols: list[str],
        timeframes: list[str],
        count: int = 500,
    ) -> dict[str, int]:
        """Utilitas: Ambil dan simpan OHLCV untuk semua kombinasi simbol+timeframe."""
        results: dict[str, int] = {}
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
                    try:
                        await session.rollback()
                        from monika.infrastructure.database.safe_ops import _safe_expunge_all

                        await _safe_expunge_all(session)
                    except Exception:
                        pass
                    results[key] = 0
        total_bars = sum(results.values())
        logger.info(f"OHLCV data sync complete: {len(results)} pairs ({total_bars} bars saved/updated)")
        return results

    async def get_current_price(self, symbol: str) -> Optional[dict[str, Any]]:
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

    async def calc_margin(
        self,
        symbol: str,
        lot: float,
        action: str = "buy",
        price: Optional[float] = None,
    ) -> dict[str, Any]:
        """Calculates margin requirement using MT5 order_calc_margin with fallback."""
        clean_sym = symbol.strip().upper().replace("/", "")
        margin = None
        if await self.ensure_connected():
            try:
                import MetaTrader5 as mt5

                action_type = mt5.ORDER_TYPE_BUY if action.lower() == "buy" else mt5.ORDER_TYPE_SELL
                if price is None:
                    tick = await self.get_current_price(clean_sym)
                    if tick:
                        price = tick["ask"] if action.lower() == "buy" else tick["bid"]
                if price:

                    def _do_calc() -> Any:
                        return mt5.order_calc_margin(action_type, clean_sym, float(lot), float(price))

                    margin = await self._run(_do_calc)
            except Exception as e:
                logger.debug(f"[{clean_sym}] MT5 order_calc_margin failed: {e}")

        if margin is None:
            from monika.domain.risk.instruments.instruments import DEFAULT_INSTRUMENTS

            spec = DEFAULT_INSTRUMENTS.get(clean_sym)
            contract = spec.contract_size if spec else (100 if "XAU" in clean_sym else 100_000)
            cur_price = price or (2650.0 if "XAU" in clean_sym else 1.1000)
            notional = float(lot) * contract * float(cur_price)
            leverage = float(self.settings.get("trading", {}).get("default_leverage", 100.0))
            margin = round(notional / leverage, 2)

        return {
            "symbol": clean_sym,
            "lot_size": lot,
            "action": action.upper(),
            "price": price,
            "required_margin_usd": margin,
            "currency": "USD",
        }

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
                from monika.application.protocol.event_bus import get_event_bus

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
        from monika.application.protocol.event_bus import TickPriceEvent

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

    async def calculate_dom_vwap(self, symbol: str, direction: str, volume: float) -> dict[str, Any]:
        """Calculates L2 DOM ladder walk VWAP and expected slippage for orders."""
        if not await self.ensure_connected():
            return {"has_dom": False, "vwap": None, "slippage_pts": 0.0, "filled_pct": 1.0}
        return await self._run(_calculate_dom_vwap, symbol, direction, volume, priority=PRIORITY_NORMAL)

    def _timeframe_to_mt5(self, timeframe: str) -> int:
        """Map timeframe string to MT5 timeframe integer constant."""
        tf_map = _build_timeframe_map()
        return tf_map.get(timeframe.upper(), 16385)

    def _resolve_timeframe(self, tf_str: str) -> Optional[int]:
        """Ubah string timeframe (mis: H1) menjadi konstanta MT5."""
        if not self._timeframe_map:
            try:
                self._timeframe_map = _build_timeframe_map()
            except Exception as e:
                logger.warning(f"Failed to build MT5 timeframe map: {e}")
                return None
        return self._timeframe_map.get(tf_str.upper())

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
