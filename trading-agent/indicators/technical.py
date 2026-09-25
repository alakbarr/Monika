# ==============================================================================
# File: indicators/technical.py
# ==============================================================================

"""
Kalkulator Indikator Teknikal (Async) berbasis library `ta`.

Menghitung dan menyimpan indikator ke tabel `technical_indicators`:
- Moving Averages (SMA, EMA)
- Momentum & Oscillators (RSI, Stochastic, MACD)
- Volatility (Bollinger Bands, ATR)
- Trend (ADX)

Hasil disimpan dalam format JSON string untuk fleksibilitas.
"""

import json
import logging
from datetime import datetime, timezone
import inspect
from typing import Optional, Any, cast

import numpy as np
import pandas as pd
import ta  # type: ignore
import ta.momentum
import ta.trend
import ta.volatility
import ta.volume
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.models import PriceOHLCV, TechnicalIndicator

logger = logging.getLogger("TradingAgent.Indicators")


def compute_yang_zhang_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Yang-Zhang (2000) historical volatility estimator.
    Handles overnight jump risk and open-to-close drift, ~14x more efficient than close-to-close.
    Source: AlphaMaster model_core/features.py, Vibe-Trading
    """
    if len(df) < window + 1:
        return pd.Series(index=df.index, dtype=float)

    n = max(2, window)
    open_p = df["open"].astype(float)
    high_p = df["high"].astype(float)
    low_p = df["low"].astype(float)
    close_p = df["close"].astype(float)

    # Log components
    log_oc = pd.Series(np.log(close_p / (open_p + 1e-12)), index=df.index)
    log_co_prev = pd.Series(np.log(open_p / (close_p.shift(1) + 1e-12)), index=df.index)
    log_ho = pd.Series(np.log(high_p / (open_p + 1e-12)), index=df.index)
    log_lo = pd.Series(np.log(low_p / (open_p + 1e-12)), index=df.index)
    log_hc = pd.Series(np.log(high_p / (close_p + 1e-12)), index=df.index)
    log_lc = pd.Series(np.log(low_p / (close_p + 1e-12)), index=df.index)

    # Rogers-Satchell component
    rs = (log_ho * log_hc + log_lo * log_lc).rolling(n).mean()

    # Overnight & open-to-close variances
    overnight_var = log_co_prev.rolling(n).var()
    oc_var = log_oc.rolling(n).var()

    k = 0.34 / (1.34 + ((n + 1) / (n - 1)))
    yz_var = overnight_var + (oc_var * k) + (rs * (1.0 - k))

    return yz_var.apply(lambda x: float(np.sqrt(max(0.0, x))) if pd.notna(x) else 0.0)


def compute_lag1_autocorrelation(close: pd.Series, window: int = 20) -> pd.Series:
    """
    Rolling lag-1 return autocorrelation for statistical regime detection.
    AC1 > 0: momentum regime (trend-following strategies favored).
    AC1 < 0: mean-reverting regime (reversals/sweeps favored).
    Source: AlphaMaster model_core/features.py
    """
    if len(close) < window + 2:
        return pd.Series(index=close.index, dtype=float)

    returns = close.astype(float).pct_change()

    def _calc_ac1(arr):
        s = pd.Series(arr)
        if len(s) < 3 or s.std() < 1e-12:
            return 0.0
        val = s.autocorr(lag=1)
        return float(val) if pd.notna(val) else 0.0

    return cast(pd.Series, returns.rolling(window).apply(_calc_ac1, raw=False))


class TechnicalIndicatorCalculator:
    """
    Menghitung dan menyimpan indikator dari data OHLCV.

    Penggunaan:
        calc = TechnicalIndicatorCalculator(session, settings)
        await calc.compute_and_save("XAUUSD", "H1")
    """

    def __init__(self, session: AsyncSession, settings: dict):
        """
        Args:
            session: Async SQLAlchemy session.
            settings: trading.indicators section from settings.yaml.
        """
        self.session = session
        cfg = settings.get("trading", {}).get("indicators", {}) or settings.get("indicators", {})
        self.ma_periods: list[int] = cfg.get("ma_periods", [20, 50, 200])
        self.rsi_period: int = cfg.get("rsi_period", 14)
        self.stoch_k: int = cfg.get("stochastic_k", 14)
        self.stoch_d: int = cfg.get("stochastic_d", 3)
        self.macd_fast: int = cfg.get("macd_fast", 12)
        self.macd_slow: int = cfg.get("macd_slow", 26)
        self.macd_signal: int = cfg.get("macd_signal", 9)
        self.bb_period: int = cfg.get("bollinger_period", 20)
        self.bb_std: int = int(cfg.get("bollinger_std", 2))
        self.atr_period: int = cfg.get("atr_period", 14)
        self.adx_period: int = cfg.get("adx_period", 14)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compute_and_save(self, symbol: str, timeframe: str) -> int:
        """
        Menjalankan alur lengkap: load OHLCV -> hitung -> simpan.

        Returns:
            Jumlah baris indikator yang disimpan.
        """
        df = await self._load_ohlcv(symbol, timeframe)
        if df is None:
            logger.warning(f"No OHLCV data for {symbol}/{timeframe}")
            return 0
            
        min_bars = max(self.ma_periods) + 5 if self.ma_periods else 30
        
        if len(df) < min_bars:
            logger.warning(
                f"Insufficient OHLCV bars for {symbol}/{timeframe}: "
                f"have {len(df)}, need {min_bars}. "
                f"{'SMA_200 requires ~205 D1 bars — wait for more history.' if timeframe == 'D1' else 'Fetch more price history.'}"
            )
            # Tetap hitung indikator yang memungkinkan dengan data terbatas
            # Lewati sepenuhnya jika data terlalu sedikit bahkan untuk RSI
            if len(df) < 20:
                return 0
                
            # Sesuaikan ma_periods hanya untuk yang bisa dihitung
            computable_periods = [p for p in self.ma_periods if p <= len(df) - 5]
            if not computable_periods:
                return 0
                
            original_periods = self.ma_periods
            self.ma_periods = computable_periods
            
            try:
                import asyncio
                indicators = await asyncio.to_thread(self._compute_all, df)
                saved = await self._save(symbol, timeframe, indicators)
            finally:
                self.ma_periods = original_periods
        else:
            import asyncio
            indicators = await asyncio.to_thread(self._compute_all, df)
            saved = await self._save(symbol, timeframe, indicators)
            
        # Wire OrderFlow snapshot calculation
        try:
            from indicators.order_flow import OrderFlowEngine
            of_engine = OrderFlowEngine(mt5_client=getattr(self, 'mt5_client', None))
            of_snapshot = await of_engine.analyze_order_flow(self.session, symbol, df=df)
            bar_ts = df.index[-1] if not df.empty else clock.now()
            if isinstance(bar_ts, pd.Timestamp):
                bar_ts = bar_ts.to_pydatetime()
            add_res: Any = self.session.add(TechnicalIndicator(
                symbol=symbol,
                timeframe=timeframe,
                indicator_name="ORDER_FLOW_SNAPSHOT",
                value_json=json.dumps(of_snapshot.to_dict()),
                timestamp=bar_ts,
            ))
            if inspect.isawaitable(add_res):
                await cast(Any, add_res)
            await self.session.commit()
        except Exception as of_err:
            logger.debug(f"OrderFlow snapshot save failed for {symbol}: {of_err}")

        logger.debug(f"Saved {saved} indicator rows for {symbol}/{timeframe}")
        return saved

    async def compute_all_symbols(
        self, symbols: list[str], timeframes: list[str]
    ) -> dict[str, int]:
        """Menjalankan komputasi untuk semua aset dan timeframe."""
        results = {}
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}/{tf}"
                try:
                    n = await self.compute_and_save(symbol, tf)
                    results[key] = n
                except Exception as e:
                    logger.error(f"Indicator computation failed for {key}: {e}")
                    results[key] = 0
        total_rows = sum(results.values())
        logger.info(f"Technical indicators complete: {len(results)} pairs ({total_rows} indicator rows computed)")
        return results

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    async def _load_ohlcv(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Memuat OHLCV secara descending, lalu dibalik menjadi kronologis untuk kalkulasi."""
        result = await self.session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())  # DESC to get most recent rows
            .limit(1000)
        )
        rows = result.scalars().all()
        if not rows:
            logger.warning(f"No OHLCV data found for {symbol}/{timeframe}")
            return None

        # Balik urutan agar kembali kronologis (ascending) untuk perhitungan indikator
        rows = list(reversed(rows))

        df = pd.DataFrame({
            "timestamp": [r.timestamp for r in rows],
            "open":  [r.open  for r in rows],
            "high":  [r.high  for r in rows],
            "low":   [r.low   for r in rows],
            "close": [r.close for r in rows],
            "volume":[r.volume for r in rows],
        })
        df.set_index("timestamp", inplace=True)
        
        # Ensure chronological monotonic index
        if not df.index.is_monotonic_increasing:
            df.sort_index(inplace=True)
            
        # Resample and forward-fill to handle missing candles without time distortion
        tf_freq_map = {
            "M1": "1min",
            "M5": "5min",
            "M15": "15min",
            "M30": "30min",
            "H1": "1h",
            "H4": "4h",
            "D1": "24h",
        }
        freq = tf_freq_map.get(timeframe.upper())
        if freq and len(df) > 1:
            try:
                deduped = df[~df.index.duplicated(keep='first')]
                resampled = deduped.resample(freq, origin='start').asfreq()
                # If resampling produced NaNs across the series, fallback to raw deduped data
                if not resampled['close'].isna().all():
                    # Filter weekend market closure bars for Forex / Commodities (non-24/7 crypto)
                    is_crypto = any(c in symbol.upper() for c in ("BTC", "ETH", "SOL"))
                    if not is_crypto:
                        idx: Any = pd.DatetimeIndex(resampled.index)
                        is_weekend = (
                            (idx.dayofweek == 5) |
                            ((idx.dayofweek == 6) & (idx.hour < 21)) |
                            ((idx.dayofweek == 4) & (idx.hour >= 22))
                        )
                        resampled = resampled[~is_weekend]
                    resampled['close'] = resampled['close'].ffill()
                    resampled['open'] = resampled['open'].fillna(resampled['close'])
                    resampled['high'] = resampled['high'].fillna(resampled['close'])
                    resampled['low'] = resampled['low'].fillna(resampled['close'])
                    resampled['volume'] = resampled['volume'].fillna(0.0)
                    if not resampled.empty and not resampled['close'].isna().all():
                        df = resampled
                    else:
                        df = deduped
                else:
                    df = deduped
            except Exception as e:
                logger.debug(f"Resampling error for {symbol}/{timeframe} (fallback to raw): {e}")
                
        return cast(Optional[pd.DataFrame], df)

    # ------------------------------------------------------------------
    # Indicator computation
    # ------------------------------------------------------------------

    def _compute_all(self, df: pd.DataFrame, is_final: bool = True) -> dict[datetime, list[dict]]:
        """
        Menghitung seluruh indikator dari DataFrame OHLCV.
        Jika is_final=False, bar forming terakhir dikecualikan untuk mencegah repainting.

        Returns:
            Dict mapping timestamp -> list of dict {name, value_json}.
        """
        if not is_final and len(df) > 1:
            df = df.iloc[:-1].copy()

        result: dict[datetime, list[dict]] = {}

        def add(ts, name: str, value):
            """Menambahkan indikator ke hasil dictionary."""
            if ts not in result:
                result[ts] = []
            result[ts].append({"name": name, "value_json": json.dumps(value)})

        close  = cast(pd.Series, df["close"])
        high   = cast(pd.Series, df["high"])
        low    = cast(pd.Series, df["low"])
        volume = cast(pd.Series, df["volume"])

        # ---- Moving Averages ----
        for period in self.ma_periods:
            sma = ta.trend.sma_indicator(close, window=period, fillna=False)
            ema = ta.trend.ema_indicator(close, window=period, fillna=False)
            for ts in df.index:
                sma_v = sma.get(ts)
                ema_v = ema.get(ts)
                if sma_v is not None and pd.notna(sma_v):
                    add(ts, f"SMA_{period}", round(float(sma_v), 5))
                if ema_v is not None and pd.notna(ema_v):
                    add(ts, f"EMA_{period}", round(float(ema_v), 5))

        # ---- RSI ----
        rsi_series = ta.momentum.rsi(close, window=self.rsi_period, fillna=False)
        for ts in df.index:
            v = rsi_series.get(ts)
            if v is not None and pd.notna(v):
                add(ts, f"RSI_{self.rsi_period}", round(float(v), 2))

        # ---- MACD ----
        macd_obj = ta.trend.MACD(
            close,
            window_fast=self.macd_fast,
            window_slow=self.macd_slow,
            window_sign=self.macd_signal,
            fillna=False,
        )
        macd_line   = macd_obj.macd()
        signal_line = macd_obj.macd_signal()
        hist        = macd_obj.macd_diff()

        for ts in df.index:
            m = macd_line.get(ts)
            s = signal_line.get(ts)
            h = hist.get(ts)
            if m is not None and pd.notna(m):
                add(ts, "MACD", {
                    "macd":      round(float(m), 5),
                    "signal":    round(float(s), 5) if (s is not None and pd.notna(s)) else None,
                    "histogram": round(float(h), 5) if (h is not None and pd.notna(h)) else None,
                })

        # ---- Bollinger Bands ----
        bb_obj = ta.volatility.BollingerBands(
            close,
            window=self.bb_period,
            window_dev=self.bb_std,
            fillna=False,
        )
        bb_upper  = bb_obj.bollinger_hband()
        bb_mid    = bb_obj.bollinger_mavg()
        bb_lower  = bb_obj.bollinger_lband()
        bb_pct    = bb_obj.bollinger_pband()
        bb_width  = bb_obj.bollinger_wband()

        for ts in df.index:
            u = bb_upper.get(ts)
            m = bb_mid.get(ts)
            l = bb_lower.get(ts)
            if (
                u is not None and m is not None and l is not None
                and pd.notna(u) and pd.notna(m) and pd.notna(l)
            ):
                p = bb_pct.get(ts)
                w = bb_width.get(ts)
                add(ts, "BBANDS", {
                    "upper": round(float(u), 5),
                    "mid":   round(float(m), 5),
                    "lower": round(float(l), 5),
                    "pct_b": round(float(p), 4) if (p is not None and pd.notna(p)) else None,
                    "width": round(float(w), 4) if (w is not None and pd.notna(w)) else None,
                })

        # ---- Stochastic ----
        stoch_obj = ta.momentum.StochasticOscillator(
            high, low, close,
            window=self.stoch_k,
            smooth_window=self.stoch_d,
            fillna=False,
        )
        stoch_k = stoch_obj.stoch()
        stoch_d_series = stoch_obj.stoch_signal()

        for ts in df.index:
            k = stoch_k.get(ts)
            d = stoch_d_series.get(ts)
            if k is not None and pd.notna(k):
                add(ts, "STOCH", {
                    "k": round(float(k), 2),
                    "d": round(float(d), 2) if (d is not None and pd.notna(d)) else None,
                })

        # ---- OBV (On-Balance Volume) ----
        try:
            if volume is not None and len(volume) > 0 and (volume > 0).any():
                obv_series = ta.volume.on_balance_volume(close, volume, fillna=False)
                for ts in df.index:
                    v = obv_series.get(ts)
                    if v is not None and pd.notna(v):
                        add(ts, "OBV", round(float(v), 2))
        except Exception as e:
            logger.debug(f"OBV computation failed: {e}")

        # ---- ATR (Average True Range) ----
        try:
            atr_series = ta.volatility.average_true_range(high, low, close, window=self.atr_period, fillna=False)
            for ts in df.index:
                v = atr_series.get(ts)
                if v is not None and pd.notna(v):
                    add(ts, f"ATR_{self.atr_period}", round(float(v), 5))
        except Exception as e:
            logger.debug(f"ATR computation failed: {e}")

        # ---- ADX (Average Directional Index) — trend strength ----
        try:
            adx_indicator = ta.trend.ADXIndicator(high, low, close, window=self.adx_period, fillna=False)
            adx_series = adx_indicator.adx()
            adx_pos = adx_indicator.adx_pos()   # +DI
            adx_neg = adx_indicator.adx_neg()   # -DI
            for ts in df.index:
                v = adx_series.get(ts)
                if v is not None and pd.notna(v):
                    pos = adx_pos.get(ts)
                    neg = adx_neg.get(ts)
                    add(ts, f"ADX_{self.adx_period}", {
                        "adx": round(float(v), 2),
                        "plus_di": round(float(pos), 2) if pos is not None and pd.notna(pos) else None,
                        "minus_di": round(float(neg), 2) if neg is not None and pd.notna(neg) else None,
                        "trending": bool(v > 25),
                        "strong": bool(v > 40),
                    })
        except Exception as e:
            logger.debug(f"ADX computation failed: {e}")

        # ---- Yang-Zhang Historical Volatility ----
        try:
            yz_series = compute_yang_zhang_volatility(df, window=20)
            for ts in df.index:
                v = yz_series.get(ts)
                if v is not None and pd.notna(v):
                    add(ts, "YANG_ZHANG_VOL_20", round(float(v), 6))
        except Exception as e:
            logger.debug(f"Yang-Zhang computation failed: {e}")

        # ---- AC1 (Lag-1 Return Autocorrelation) ----
        try:
            ac1_series = compute_lag1_autocorrelation(close, window=20)
            for ts in df.index:
                v = ac1_series.get(ts)
                if v is not None and pd.notna(v):
                    add(ts, "AC1_20", round(float(v), 4))
        except Exception as e:
            logger.debug(f"AC1 computation failed: {e}")

        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _save(
        self,
        symbol: str,
        timeframe: str,
        indicators: dict[datetime, list[dict]],
    ) -> int:
        """
        Menyimpan indikator (upsert per timestamp) agar data sinkron
        dengan bar/candle terbaru.
        """
        timestamps = list(indicators.keys())
        if not timestamps:
            return 0

        await self.session.execute(
            delete(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.timestamp.in_(timestamps))
        )

        saved = 0
        for ts, entries in indicators.items():
            for entry in entries:
                self.session.add(TechnicalIndicator(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    indicator_name=entry["name"],
                    value_json=entry["value_json"],
                ))
                saved += 1

        await self.session.commit()
        return saved

    # ------------------------------------------------------------------
    # Read helpers (used by analysis stage)
    # ------------------------------------------------------------------

    async def get_latest(
        self, symbol: str, timeframe: str, indicator_name: str
    ) -> Optional[dict]:
        """Mengambil metrik indikator terbaru untuk suatu symbol/timeframe."""
        result = await self.session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.indicator_name == indicator_name)
            .where(TechnicalIndicator.timestamp <= clock.now())
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {"timestamp": row.timestamp, "value": json.loads(row.value_json)}

    async def get_snapshot(self, symbol: str, timeframe: str) -> dict:
        """
        Mengambil semua nilai indikator pada timestamp terkini dengan konteks delta dan arah.
        Berguna untuk ringkasan data yang diumpankan ke agent.
        """
        recent_ts_result = await self.session.execute(
            select(TechnicalIndicator.timestamp)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.timestamp <= clock.now())
            .group_by(TechnicalIndicator.timestamp)
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(2)
        )
        recent_ts = recent_ts_result.scalars().all()
        if not recent_ts:
            return {}

        latest_ts = recent_ts[0]
        prev_ts = recent_ts[1] if len(recent_ts) > 1 else None

        result_latest = await self.session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.timestamp == latest_ts)
        )
        latest_rows = result_latest.scalars().all()

        prev_map = {}
        if prev_ts:
            result_prev = await self.session.execute(
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == timeframe)
                .where(TechnicalIndicator.timestamp == prev_ts)
            )
            prev_map = {r.indicator_name: json.loads(r.value_json) for r in result_prev.scalars().all()}

        def _extract_scalar(val: Any) -> Optional[float]:
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                for k in ("rsi", "histogram", "macd", "adx", "k", "pct_b", "atr", "value"):
                    if k in val and isinstance(val[k], (int, float)):
                        return float(val[k])
            return None

        snapshot = {}
        for row in latest_rows:
            curr_val = json.loads(row.value_json)
            prev_val = prev_map.get(row.indicator_name)
            curr_num = _extract_scalar(curr_val)
            prev_num = _extract_scalar(prev_val) if prev_val is not None else None

            delta = None
            direction = "flat"
            if curr_num is not None and prev_num is not None:
                delta = round(curr_num - prev_num, 5)
                threshold = 0.0001 if abs(curr_num) < 10 else 0.01
                if delta > threshold:
                    direction = "rising"
                elif delta < -threshold:
                    direction = "falling"

            snapshot[row.indicator_name] = {
                "timestamp": row.timestamp,
                "value": curr_val,
                "prev": prev_val,
                "delta": delta,
                "direction": direction,
            }

        return snapshot
