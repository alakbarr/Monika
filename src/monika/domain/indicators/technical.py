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
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from monika.core.serialization import fast_json

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


def _append_scalar_series(
    result_map: dict[datetime, list[dict[str, Any]]],
    keys: list[datetime],
    name: str,
    series: Optional[pd.Series],
    n_target: int,
    decimals: int,
) -> None:
    if series is None or len(series) == 0:
        return
    arr = series.to_numpy(dtype=float)[-n_target:]
    for idx, ts in enumerate(keys):
        v = arr[idx]
        if not np.isnan(v):
            result_map[ts].append({"name": name, "value_json": fast_json.dumps(round(float(v), decimals))})


def _append_macd(
    result_map: dict[datetime, list[dict[str, Any]]],
    keys: list[datetime],
    macd_line: Optional[pd.Series],
    signal_line: Optional[pd.Series],
    hist_line: Optional[pd.Series],
    n_target: int,
) -> None:
    if macd_line is None or len(macd_line) == 0:
        return
    m_arr = macd_line.to_numpy(dtype=float)[-n_target:]
    s_arr = signal_line.to_numpy(dtype=float)[-n_target:] if signal_line is not None else None
    h_arr = hist_line.to_numpy(dtype=float)[-n_target:] if hist_line is not None else None

    for idx, ts in enumerate(keys):
        m = m_arr[idx]
        if not np.isnan(m):
            s = s_arr[idx] if s_arr is not None else np.nan
            h = h_arr[idx] if h_arr is not None else np.nan
            result_map[ts].append(
                {
                    "name": "MACD",
                    "value_json": fast_json.dumps(
                        {
                            "macd": round(float(m), 5),
                            "signal": round(float(s), 5) if not np.isnan(s) else None,
                            "histogram": round(float(h), 5) if not np.isnan(h) else None,
                        }
                    ),
                }
            )


def _append_bollinger(
    result_map: dict[datetime, list[dict[str, Any]]],
    keys: list[datetime],
    upper: Optional[pd.Series],
    mid: Optional[pd.Series],
    lower: Optional[pd.Series],
    pct_b: Optional[pd.Series],
    width: Optional[pd.Series],
    n_target: int,
) -> None:
    if upper is None or mid is None or lower is None or len(upper) == 0:
        return
    u_arr = upper.to_numpy(dtype=float)[-n_target:]
    m_arr = mid.to_numpy(dtype=float)[-n_target:]
    l_arr = lower.to_numpy(dtype=float)[-n_target:]
    p_arr = pct_b.to_numpy(dtype=float)[-n_target:] if pct_b is not None else None
    w_arr = width.to_numpy(dtype=float)[-n_target:] if width is not None else None

    for idx, ts in enumerate(keys):
        u, m, l = u_arr[idx], m_arr[idx], l_arr[idx]
        if not np.isnan(u) and not np.isnan(m) and not np.isnan(l):
            p = p_arr[idx] if p_arr is not None else np.nan
            w = w_arr[idx] if w_arr is not None else np.nan
            result_map[ts].append(
                {
                    "name": "BBANDS",
                    "value_json": fast_json.dumps(
                        {
                            "upper": round(float(u), 5),
                            "mid": round(float(m), 5),
                            "lower": round(float(l), 5),
                            "pct_b": round(float(p), 4) if not np.isnan(p) else None,
                            "width": round(float(w), 4) if not np.isnan(w) else None,
                        }
                    ),
                }
            )


def _append_stochastic(
    result_map: dict[datetime, list[dict[str, Any]]],
    keys: list[datetime],
    k_series: Optional[pd.Series],
    d_series: Optional[pd.Series],
    n_target: int,
) -> None:
    if k_series is None or len(k_series) == 0:
        return
    k_arr = k_series.to_numpy(dtype=float)[-n_target:]
    d_arr = d_series.to_numpy(dtype=float)[-n_target:] if d_series is not None else None

    for idx, ts in enumerate(keys):
        k_val = k_arr[idx]
        if not np.isnan(k_val):
            d_val = d_arr[idx] if d_arr is not None else np.nan
            result_map[ts].append(
                {
                    "name": "STOCH",
                    "value_json": fast_json.dumps(
                        {
                            "k": round(float(k_val), 2),
                            "d": round(float(d_val), 2) if not np.isnan(d_val) else None,
                        }
                    ),
                }
            )


def _append_adx(
    result_map: dict[datetime, list[dict[str, Any]]],
    keys: list[datetime],
    period: int,
    adx_series: Optional[pd.Series],
    plus_di: Optional[pd.Series],
    minus_di: Optional[pd.Series],
    n_target: int,
) -> None:
    if adx_series is None or len(adx_series) == 0:
        return
    a_arr = adx_series.to_numpy(dtype=float)[-n_target:]
    p_arr = plus_di.to_numpy(dtype=float)[-n_target:] if plus_di is not None else None
    m_arr = minus_di.to_numpy(dtype=float)[-n_target:] if minus_di is not None else None

    for idx, ts in enumerate(keys):
        v = a_arr[idx]
        if not np.isnan(v):
            pos = p_arr[idx] if p_arr is not None else np.nan
            neg = m_arr[idx] if m_arr is not None else np.nan
            result_map[ts].append(
                {
                    "name": f"ADX_{period}",
                    "value_json": fast_json.dumps(
                        {
                            "adx": round(float(v), 2),
                            "plus_di": round(float(pos), 2) if not np.isnan(pos) else None,
                            "minus_di": round(float(neg), 2) if not np.isnan(neg) else None,
                            "trending": bool(v > 25),
                            "strong": bool(v > 40),
                        }
                    ),
                }
            )


_SERVICE_CLS: Optional[type] = None


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
        Vectorized contiguous slicing implementation with zero closure definitions.
        """
        if df is None or len(df) == 0:
            return {}

        required_cols = ("open", "high", "low", "close", "volume")
        if not all(col in df.columns for col in required_cols):
            return {}

        if not is_final and len(df) > 1:
            df = df.iloc[:-1].copy()

        target_df = df.iloc[-100:] if len(df) > 100 else df
        n_target = len(target_df)

        # Normalize target index to datetime keys
        keys: list[datetime] = []
        for t in target_df.index:
            if hasattr(t, "to_pydatetime"):
                keys.append(t.to_pydatetime())
            elif isinstance(t, (int, float)):
                keys.append(datetime.fromtimestamp(float(t), tz=timezone.utc))
            else:
                p_ts = pd.to_datetime(t)
                keys.append(p_ts.to_pydatetime() if hasattr(p_ts, "to_pydatetime") else t)

        result: dict[datetime, list[dict[str, Any]]] = {ts: [] for ts in keys}

        close = pd.Series(df["close"])
        high = pd.Series(df["high"])
        low = pd.Series(df["low"])

        # 1. Moving Averages (Rust C-ABI Accelerated)
        ma_dict = compute_moving_averages(
            close,
            sma_periods=tuple(self.ma_periods),
            ema_periods=tuple(self.ma_periods),
        )
        for period in self.ma_periods:
            _append_scalar_series(result, keys, f"SMA_{period}", ma_dict.get(f"SMA_{period}"), n_target, 5)
            _append_scalar_series(result, keys, f"EMA_{period}", ma_dict.get(f"EMA_{period}"), n_target, 5)

        # 2. RSI (Rust C-ABI Accelerated)
        rsi_series = compute_rsi(close, period=self.rsi_period)
        _append_scalar_series(result, keys, f"RSI_{self.rsi_period}", rsi_series, n_target, 2)

        # 3. MACD (Rust C-ABI Accelerated)
        macd_line, signal_line, hist = compute_macd(
            close,
            fast=self.macd_fast,
            slow=self.macd_slow,
            signal=self.macd_signal,
        )
        _append_macd(result, keys, macd_line, signal_line, hist, n_target)

        # 4. Bollinger Bands (Rust C-ABI Accelerated)
        bb_upper, bb_mid, bb_lower, bb_pct, bb_width = compute_bollinger_bands(
            close,
            period=self.bb_period,
            std_dev=float(self.bb_std),
        )
        _append_bollinger(result, keys, bb_upper, bb_mid, bb_lower, bb_pct, bb_width, n_target)

        # 5. Stochastic (Rust C-ABI Accelerated)
        stoch_k_series, stoch_d_series = compute_stochastic(
            high,
            low,
            close,
            k_period=self.stoch_k,
            d_period=self.stoch_d,
        )
        _append_stochastic(result, keys, stoch_k_series, stoch_d_series, n_target)

        # 5.5 OBV (On-Balance Volume)
        volume = pd.Series(df["volume"]) if "volume" in df.columns else None
        try:
            if volume is not None and len(volume) > 0 and (volume > 0).any():
                from monika.domain.indicators.workspace_indicators import compute_obv

                obv_series = compute_obv(close, volume)
                _append_scalar_series(result, keys, "OBV", obv_series, n_target, 2)
        except Exception as e:
            logger.debug(f"OBV computation failed: {e}")

        # 6. ATR (Rust C-ABI Accelerated)
        try:
            atr_series = compute_atr(high, low, close, period=self.atr_period)
            _append_scalar_series(result, keys, f"ATR_{self.atr_period}", atr_series, n_target, 5)
        except Exception as e:
            logger.debug(f"ATR computation failed: {e}")

        # 7. ADX
        try:
            adx_series, adx_pos, adx_neg = compute_adx(high, low, close, period=self.adx_period)
            _append_adx(result, keys, self.adx_period, adx_series, adx_pos, adx_neg, n_target)
        except Exception as e:
            logger.debug(f"ADX computation failed: {e}")

        # 8. Yang-Zhang Historical Volatility
        try:
            yz_series = compute_yang_zhang_volatility(df, window=20)
            _append_scalar_series(result, keys, "YANG_ZHANG_VOL_20", yz_series, n_target, 6)
        except Exception as e:
            logger.debug(f"Yang-Zhang computation failed: {e}")

        # 9. Autocorrelation (AC1)
        try:
            ac1_series = compute_lag1_autocorrelation(close, window=20)
            _append_scalar_series(result, keys, "AC1_20", ac1_series, n_target, 4)
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
