# ==============================================================================
# File: domain/indicators/technical.py
# ==============================================================================

"""
Kalkulator Indikator Teknikal Murni (Pure Domain Indicators) & Facade.

Menghitung indikator teknikal murni dari pandas DataFrame / Series tanpa I/O database:
- Moving Averages (SMA, EMA, WMA, VWAP)
- Momentum & Oscillators (RSI, Stochastic, MACD)
- Volatility (Bollinger Bands, ATR, Yang-Zhang, Supertrend, Keltner)
- Trend (ADX, Supertrend)
- Autocorrelation (AC1)
- Pivot Points & Ichimoku Kinko Hyo
- Divergence Detection (RSI, MACD)
- Chart Workspace Indicator Evaluation Engine

Untuk orkestrasi pemuatan OHLCV dari database dan penyimpanan ke database,
lihat monika.application.services.technical_indicator_service.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd
import ta
import ta.momentum
import ta.trend
import ta.volatility
import ta.volume

from monika.domain.indicators.classic import (
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_ichimoku,
    compute_lag1_autocorrelation,
    compute_macd,
    compute_moving_averages,
    compute_pivot_points,
    compute_rsi,
    compute_stochastic,
    compute_yang_zhang_volatility,
    detect_macd_divergence,
    detect_rsi_divergence,
)
from monika.domain.indicators.workspace_indicators import (
    CHART_WORKSPACE_PRESETS,
    DEFAULT_CHART_WORKSPACE_CONFIG,
    _clamp_float,
    _clamp_int,
    _extract_unix_timestamps,
    compute_cvd_series,
    compute_donchian_channels,
    compute_ichimoku_series,
    compute_keltner_channels,
    compute_obv,
    compute_supertrend,
    compute_vwap,
    compute_wma,
    evaluate_workspace_indicators,
    normalize_chart_workspace_config,
)

logger = logging.getLogger("TradingAgent.Indicators")


class TechnicalIndicatorCalculator:
    """
    Pure Domain Technical Indicator Calculator.
    Calculates technical indicators on pandas DataFrame in-memory without database dependencies.
    When instantiated with a database session, delegates to registered TechnicalIndicatorService for DB persistence.
    """

    @classmethod
    def register_service_class(cls, service_cls: type) -> None:
        """Register the application service class for DB persistence."""
        global _SERVICE_CLS
        _SERVICE_CLS = service_cls

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        global _SERVICE_CLS
        if cls is TechnicalIndicatorCalculator and _SERVICE_CLS is not None:
            session = kwargs.get("session") if "session" in kwargs else (args[0] if len(args) > 0 else None)
            if session is not None:
                return super().__new__(_SERVICE_CLS)
        return super().__new__(cls)

    def __init__(self, session: Any = None, settings: Optional[dict] = None):
        """
        Args:
            session: Optional session (ignored in pure domain detector, kept for signature compatibility).
            settings: trading.indicators section from settings.yaml.
        """
        self.session = session
        cfg = (settings or {}).get("trading", {}).get("indicators", {}) or (settings or {}).get("indicators", {})
        self.ma_periods: list[int] = cfg.get("ma_periods", [20, 50, 200])
        self.rsi_period: int = cfg.get("rsi_period", 14)
        self.stoch_k: int = cfg.get("stochastic_k", 14)
        self.stoch_d: int = cfg.get("stochastic_d", 3)
        self.macd_fast: int = cfg.get("macd_fast", 12)
        self.macd_slow: int = cfg.get("macd_slow", 26)
        self.macd_signal: int = cfg.get("macd_signal", 9)
        self.bb_period: int = cfg.get("bollinger_period", 20)
        self.bb_std: float = float(cfg.get("bollinger_std", 2.0))
        self.atr_period: int = cfg.get("atr_period", 14)
        self.adx_period: int = cfg.get("adx_period", 14)

    def _compute_all(self, df: pd.DataFrame, is_final: bool = True) -> dict[datetime, list[dict[str, Any]]]:
        """
        Menghitung seluruh indikator dari DataFrame OHLCV secara in-memory.
        """
        if df is None or len(df) == 0:
            return {}

        required_cols = ("open", "high", "low", "close", "volume")
        if not all(col in df.columns for col in required_cols):
            return {}

        if not is_final and len(df) > 1:
            df = df.iloc[:-1].copy()

        result: dict[datetime, list[dict[str, Any]]] = {}

        try:
            import orjson

            def _fast_dumps(val: Any) -> str:
                return orjson.dumps(val).decode("utf-8")
        except ImportError:
            import json

            def _fast_dumps(val: Any) -> str:
                return json.dumps(val)

        def add(ts: Any, name: str, value: Any) -> None:
            if ts not in result:
                result[ts] = []
            result[ts].append({"name": name, "value_json": _fast_dumps(value)})

        close = pd.Series(df["close"])
        high = pd.Series(df["high"])
        low = pd.Series(df["low"])

        target_index = df.index[-100:] if len(df) > 100 else df.index

        # 1. Moving Averages (Rust C-ABI Accelerated)
        ma_dict = compute_moving_averages(
            close,
            sma_periods=tuple(self.ma_periods),
            ema_periods=tuple(self.ma_periods),
        )
        for period in self.ma_periods:
            sma_s = ma_dict.get(f"SMA_{period}")
            if sma_s is not None:
                for ts in target_index:
                    sma_v = sma_s.get(ts)
                    if sma_v is not None and pd.notna(sma_v):
                        add(ts, f"SMA_{period}", round(float(sma_v), 5))
            ema_s = ma_dict.get(f"EMA_{period}")
            if ema_s is not None:
                for ts in target_index:
                    ema_v = ema_s.get(ts)
                    if ema_v is not None and pd.notna(ema_v):
                        add(ts, f"EMA_{period}", round(float(ema_v), 5))

        # 2. RSI (Rust C-ABI Accelerated)
        rsi_series = compute_rsi(close, period=self.rsi_period)
        for ts in target_index:
            v = rsi_series.get(ts)
            if v is not None and pd.notna(v):
                add(ts, f"RSI_{self.rsi_period}", round(float(v), 2))

        # 3. MACD (Rust C-ABI Accelerated)
        macd_line, signal_line, hist = compute_macd(
            close,
            fast=self.macd_fast,
            slow=self.macd_slow,
            signal=self.macd_signal,
        )

        for ts in target_index:
            m = macd_line.get(ts)
            s = signal_line.get(ts)
            h = hist.get(ts)
            if m is not None and pd.notna(m):
                add(
                    ts,
                    "MACD",
                    {
                        "macd": round(float(m), 5),
                        "signal": round(float(s), 5) if (s is not None and pd.notna(s)) else None,
                        "histogram": round(float(h), 5) if (h is not None and pd.notna(h)) else None,
                    },
                )

        # 4. Bollinger Bands (Rust C-ABI Accelerated)
        bb_upper, bb_mid, bb_lower, bb_pct, bb_width = compute_bollinger_bands(
            close,
            period=self.bb_period,
            std_dev=float(self.bb_std),
        )

        for ts in target_index:
            u = bb_upper.get(ts)
            m = bb_mid.get(ts)
            l = bb_lower.get(ts)
            if u is not None and m is not None and l is not None and pd.notna(u) and pd.notna(m) and pd.notna(l):
                p = bb_pct.get(ts)
                w = bb_width.get(ts)
                add(
                    ts,
                    "BBANDS",
                    {
                        "upper": round(float(u), 5),
                        "mid": round(float(m), 5),
                        "lower": round(float(l), 5),
                        "pct_b": round(float(p), 4) if (p is not None and pd.notna(p)) else None,
                        "width": round(float(w), 4) if (w is not None and pd.notna(w)) else None,
                    },
                )

        # 5. Stochastic (Rust C-ABI Accelerated)
        stoch_k_series, stoch_d_series = compute_stochastic(
            high,
            low,
            close,
            k_period=self.stoch_k,
            d_period=self.stoch_d,
        )

        for ts in target_index:
            k_val = stoch_k_series.get(ts)
            d_val = stoch_d_series.get(ts)
            if k_val is not None and pd.notna(k_val):
                add(
                    ts,
                    "STOCH",
                    {
                        "k": round(float(k_val), 2),
                        "d": round(float(d_val), 2) if (d_val is not None and pd.notna(d_val)) else None,
                    },
                )

        # 5.5 OBV (On-Balance Volume)
        volume = pd.Series(df["volume"]) if "volume" in df.columns else None
        try:
            if volume is not None and len(volume) > 0 and (volume > 0).any():
                from monika.domain.indicators.workspace_indicators import compute_obv

                obv_series = compute_obv(close, volume)
                for ts in target_index:
                    v = obv_series.get(ts)
                    if v is not None and pd.notna(v):
                        add(ts, "OBV", round(float(v), 2))
        except Exception as e:
            logger.debug(f"OBV computation failed: {e}")

        # 6. ATR (Rust C-ABI Accelerated)
        try:
            atr_series = compute_atr(high, low, close, period=self.atr_period)
            for ts in target_index:
                v = atr_series.get(ts)
                if v is not None and pd.notna(v):
                    add(ts, f"ATR_{self.atr_period}", round(float(v), 5))
        except Exception as e:
            logger.debug(f"ATR computation failed: {e}")

        # 7. ADX
        try:
            adx_series, adx_pos, adx_neg = compute_adx(high, low, close, period=self.adx_period)
            for ts in target_index:
                v = adx_series.get(ts)
                if v is not None and pd.notna(v):
                    pos = adx_pos.get(ts)
                    neg = adx_neg.get(ts)
                    add(
                        ts,
                        f"ADX_{self.adx_period}",
                        {
                            "adx": round(float(v), 2),
                            "plus_di": round(float(pos), 2) if pos is not None and pd.notna(pos) else None,
                            "minus_di": round(float(neg), 2) if neg is not None and pd.notna(neg) else None,
                            "trending": bool(v > 25),
                            "strong": bool(v > 40),
                        },
                    )
        except Exception as e:
            logger.debug(f"ADX computation failed: {e}")

        # 8. Yang-Zhang Historical Volatility
        try:
            yz_series = compute_yang_zhang_volatility(df, window=20)
            for ts in target_index:
                v = yz_series.get(ts)
                if v is not None and pd.notna(v):
                    add(ts, "YANG_ZHANG_VOL_20", round(float(v), 6))
        except Exception as e:
            logger.debug(f"Yang-Zhang computation failed: {e}")

        # 9. Autocorrelation (AC1)
        try:
            ac1_series = compute_lag1_autocorrelation(close, window=20)
            for ts in target_index:
                v = ac1_series.get(ts)
                if v is not None and pd.notna(v):
                    add(ts, "AC1_20", round(float(v), 4))
        except Exception as e:
            logger.debug(f"AC1 computation failed: {e}")

        return result

    async def compute_and_save(self, symbol: str, timeframe: str) -> int:
        """Contract stub for indicator calculation and persistence. Overridden by TechnicalIndicatorService."""
        return 0

    async def compute_all_symbols(self, symbols: list[str], timeframes: list[str]) -> dict[str, int]:
        """Contract stub for batch computation. Overridden by TechnicalIndicatorService."""
        results: dict[str, int] = {}
        for s in symbols:
            for tf in timeframes:
                key = f"{s}/{tf}"
                try:
                    results[key] = await self.compute_and_save(s, tf)
                except Exception:
                    if hasattr(self, "session") and self.session is not None:
                        try:
                            await self.session.rollback()
                            if hasattr(self.session, "expunge_all"):
                                exp = self.session.expunge_all()
                                import inspect

                                if inspect.isawaitable(exp):
                                    await exp
                        except Exception:
                            pass
                    results[key] = 0
        return results

    async def get_snapshot(
        self, symbol: str, timeframe: str, series_depth: int = 15, as_of: Optional[datetime] = None
    ) -> dict[str, Any]:
        """Contract stub for indicator snapshot. Overridden by TechnicalIndicatorService."""
        return {}

    async def get_latest(self, symbol: str, timeframe: str, indicator_name: str) -> Optional[dict[str, Any]]:
        """Contract stub for latest indicator. Overridden by TechnicalIndicatorService."""
        return None


__all__ = [
    "CHART_WORKSPACE_PRESETS",
    "DEFAULT_CHART_WORKSPACE_CONFIG",
    "TechnicalIndicatorCalculator",
    "_clamp_float",
    "_clamp_int",
    "_extract_unix_timestamps",
    "compute_adx",
    "compute_atr",
    "compute_bollinger_bands",
    "compute_cvd_series",
    "compute_donchian_channels",
    "compute_ichimoku",
    "compute_ichimoku_series",
    "compute_keltner_channels",
    "compute_lag1_autocorrelation",
    "compute_macd",
    "compute_moving_averages",
    "compute_obv",
    "compute_pivot_points",
    "compute_rsi",
    "compute_stochastic",
    "compute_supertrend",
    "compute_vwap",
    "compute_wma",
    "compute_yang_zhang_volatility",
    "detect_macd_divergence",
    "detect_rsi_divergence",
    "evaluate_workspace_indicators",
    "normalize_chart_workspace_config",
]
