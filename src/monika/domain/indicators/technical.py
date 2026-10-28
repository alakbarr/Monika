# ==============================================================================
# File: indicators/technical.py
# ==============================================================================

"""
Kalkulator Indikator Teknikal Murni (Pure Domain Indicators).

Menghitung indikator teknikal murni dari pandas DataFrame / Series tanpa I/O database:
- Moving Averages (SMA, EMA)
- Momentum & Oscillators (RSI, Stochastic, MACD)
- Volatility (Bollinger Bands, ATR, Yang-Zhang)
- Trend (ADX)
- Autocorrelation (AC1)
- Pivot Points & Ichimoku Kinko Hyo
- Divergence Detection (RSI, MACD)

Untuk orkestrasi pemuatan OHLCV dari database dan penyimpanan ke database,
lihat monika.application.services.technical_indicator_service.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
import ta
import ta.momentum
import ta.trend
import ta.volatility
import ta.volume

logger = logging.getLogger("TradingAgent.Indicators")


# ------------------------------------------------------------------
# Pure Statistical & Volatility Functions
# ------------------------------------------------------------------


def compute_yang_zhang_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Yang-Zhang (2000) historical volatility estimator.
    Handles overnight jump risk and open-to-close drift, ~14x more efficient than close-to-close.
    """
    if df is None or len(df) < window + 1:
        return pd.Series(index=df.index if df is not None else [], dtype=float)

    n = max(2, window)
    open_p = df["open"].astype(float).clip(lower=1e-6)
    high_p = df["high"].astype(float).clip(lower=open_p)
    low_p = df["low"].astype(float).clip(lower=1e-6)
    close_p = df["close"].astype(float).clip(lower=1e-6)

    # Log components
    log_oc = pd.Series(np.log(close_p / (open_p + 1e-12)), index=df.index)
    log_co_prev = pd.Series(np.log(open_p / (close_p.shift(1) + 1e-12)), index=df.index)
    log_ho = pd.Series(np.log(high_p / (open_p + 1e-12)), index=df.index)
    log_lo = pd.Series(np.log(low_p / (open_p + 1e-12)), index=df.index)
    log_hc = pd.Series(np.log(high_p / (close_p + 1e-12)), index=df.index)
    log_lc = pd.Series(np.log(low_p / (close_p + 1e-12)), index=df.index)

    # Rogers-Satchell component
    rs = pd.Series((log_ho * log_hc + log_lo * log_lc).rolling(n).mean(), index=df.index)

    # Overnight & open-to-close variances
    overnight_var = pd.Series(log_co_prev.rolling(n).var(), index=df.index)
    oc_var = pd.Series(log_oc.rolling(n).var(), index=df.index)

    k = 0.34 / (1.34 + ((n + 1) / (n - 1)))
    yz_var = pd.Series(overnight_var + (oc_var * k) + (rs * (1.0 - k)), index=df.index)

    return pd.Series(yz_var.apply(lambda x: float(np.sqrt(max(0.0, x))) if pd.notna(x) else 0.0), index=df.index)


def compute_lag1_autocorrelation(close: pd.Series, window: int = 20) -> pd.Series:
    """
    Menghitung lag-1 return autocorrelation rolling window.
    Indikator regime: AC1 > 0 menandakan momentum/trending, AC1 < 0 mean-reverting.
    """
    if close is None or len(close) < window + 2:
        return pd.Series(index=close.index if close is not None else [], dtype=float)

    returns = close.astype(float).pct_change()
    r_lag = returns.shift(1)
    ac1 = returns.rolling(window).corr(r_lag).fillna(0.0).clip(-1.0, 1.0)
    return pd.Series(ac1)


# ------------------------------------------------------------------
# Pure Indicator Computation Functions
# ------------------------------------------------------------------


def compute_moving_averages(
    close: pd.Series,
    sma_periods: tuple[int, ...] = (20, 50, 200),
    ema_periods: tuple[int, ...] = (9, 21, 50, 200),
) -> dict[str, pd.Series]:
    """Computes SMAs and EMAs for specified periods."""
    result: dict[str, pd.Series] = {}
    for p in sma_periods:
        result[f"SMA_{p}"] = pd.Series(ta.trend.sma_indicator(close, window=p, fillna=False))
    for p in ema_periods:
        result[f"EMA_{p}"] = pd.Series(ta.trend.ema_indicator(close, window=p, fillna=False))
    return result


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Computes RSI (Relative Strength Index)."""
    return pd.Series(ta.momentum.rsi(close, window=period, fillna=False))


def compute_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Computes Stochastic %K and %D."""
    stoch = ta.momentum.StochasticOscillator(
        high=high, low=low, close=close, window=k_period, smooth_window=d_period, fillna=False
    )
    return pd.Series(stoch.stoch()), pd.Series(stoch.stoch_signal())


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Computes MACD line, signal line, and histogram."""
    macd_obj = ta.trend.MACD(close, window_fast=fast, window_slow=slow, window_sign=signal, fillna=False)
    return pd.Series(macd_obj.macd()), pd.Series(macd_obj.macd_signal()), pd.Series(macd_obj.macd_diff())


def compute_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Computes Bollinger Bands: upper, middle, lower, pct_b, bandwidth."""
    bb = ta.volatility.BollingerBands(close=close, window=period, window_dev=int(std_dev), fillna=False)
    return (
        pd.Series(bb.bollinger_hband()),
        pd.Series(bb.bollinger_mavg()),
        pd.Series(bb.bollinger_lband()),
        pd.Series(bb.bollinger_pband()),
        pd.Series(bb.bollinger_wband()),
    )


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Computes Average True Range."""
    return pd.Series(ta.volatility.average_true_range(high=high, low=low, close=close, window=period, fillna=False))


def compute_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Computes ADX, +DI, and -DI."""
    adx_obj = ta.trend.ADXIndicator(high=high, low=low, close=close, window=period, fillna=False)
    return pd.Series(adx_obj.adx()), pd.Series(adx_obj.adx_pos()), pd.Series(adx_obj.adx_neg())


def compute_pivot_points(high: float, low: float, close: float, method: str = "classic") -> dict[str, Any]:
    """
    Menghitung Classical / Camarilla / Fibonacci / Woodie Pivot Points dari satu bar D1/W1.
    """
    if method == "fibonacci":
        pp = (high + low + close) / 3.0
        rng = high - low
        return {
            "pivot": round(pp, 5),
            "r1": round(pp + 0.382 * rng, 5),
            "r2": round(pp + 0.618 * rng, 5),
            "r3": round(pp + 1.0 * rng, 5),
            "s1": round(pp - 0.382 * rng, 5),
            "s2": round(pp - 0.618 * rng, 5),
            "s3": round(pp - 1.0 * rng, 5),
        }
    elif method == "camarilla":
        rng = high - low
        return {
            "pivot": round((high + low + close) / 3.0, 5),
            "r4": round(close + rng * 1.1 / 2, 5),
            "r3": round(close + rng * 1.1 / 4, 5),
            "r2": round(close + rng * 1.1 / 6, 5),
            "r1": round(close + rng * 1.1 / 12, 5),
            "s1": round(close - rng * 1.1 / 12, 5),
            "s2": round(close - rng * 1.1 / 6, 5),
            "s3": round(close - rng * 1.1 / 4, 5),
            "s4": round(close - rng * 1.1 / 2, 5),
        }
    elif method == "woodie":
        pp = (high + low + 2.0 * close) / 4.0
        rng = high - low
        return {
            "pivot": round(pp, 5),
            "r1": round(2.0 * pp - low, 5),
            "r2": round(pp + rng, 5),
            "s1": round(2.0 * pp - high, 5),
            "s2": round(pp - rng, 5),
        }
    elif method == "all":
        return {
            "classic": compute_pivot_points(high, low, close, method="classic"),
            "fibonacci": compute_pivot_points(high, low, close, method="fibonacci"),
            "camarilla": compute_pivot_points(high, low, close, method="camarilla"),
            "woodie": compute_pivot_points(high, low, close, method="woodie"),
        }
    else:  # classic
        pp = (high + low + close) / 3.0
        return {
            "pivot": round(pp, 5),
            "r1": round(2 * pp - low, 5),
            "r2": round(pp + (high - low), 5),
            "r3": round(high + 2 * (pp - low), 5),
            "s1": round(2 * pp - high, 5),
            "s2": round(pp - (high - low), 5),
            "s3": round(low - 2 * (high - pp), 5),
        }


def compute_ichimoku(
    df: pd.DataFrame,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
) -> dict[str, Any]:
    """
    Menghitung komponen Ichimoku Kinko Hyo:
    - Tenkan-sen (Conversion Line)
    - Kijun-sen (Base Line)
    - Senkou Span A (Leading Span A)
    - Senkou Span B (Leading Span B)
    - Chikou Span (Lagging Span)
    """
    if df is None or len(df) < senkou_b_period:
        return {"status": "unavailable"}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tenkan = (
        pd.Series(high.rolling(tenkan_period).max(), index=df.index)
        + pd.Series(low.rolling(tenkan_period).min(), index=df.index)
    ) / 2.0
    kijun = (
        pd.Series(high.rolling(kijun_period).max(), index=df.index)
        + pd.Series(low.rolling(kijun_period).min(), index=df.index)
    ) / 2.0
    senkou_a = ((tenkan + kijun) / 2.0).shift(kijun_period)
    senkou_b = (
        (
            pd.Series(high.rolling(senkou_b_period).max(), index=df.index)
            + pd.Series(low.rolling(senkou_b_period).min(), index=df.index)
        )
        / 2.0
    ).shift(kijun_period)
    chikou = close.shift(-kijun_period)

    last_ts = df.index[-1]
    last_close = float(close.iloc[-1])
    tk_val = float(tenkan.iloc[-1]) if pd.notna(tenkan.iloc[-1]) else None
    kj_val = float(kijun.iloc[-1]) if pd.notna(kijun.iloc[-1]) else None
    sa_val = float(senkou_a.iloc[-1]) if pd.notna(senkou_a.iloc[-1]) else None
    sb_val = float(senkou_b.iloc[-1]) if pd.notna(senkou_b.iloc[-1]) else None
    ck_val = float(chikou.iloc[-1]) if pd.notna(chikou.iloc[-1]) else last_close

    # Cloud position
    cloud_color = "neutral"
    price_vs_cloud = "inside"
    if sa_val is not None and sb_val is not None:
        cloud_color = "bullish" if sa_val > sb_val else "bearish"
        cloud_top = max(sa_val, sb_val)
        cloud_bottom = min(sa_val, sb_val)
        if last_close > cloud_top:
            price_vs_cloud = "above"
        elif last_close < cloud_bottom:
            price_vs_cloud = "below"

    return {
        "status": "success",
        "tenkan_sen": round(tk_val, 5) if tk_val is not None else None,
        "kijun_sen": round(kj_val, 5) if kj_val is not None else None,
        "senkou_span_a": round(sa_val, 5) if sa_val is not None else None,
        "senkou_span_b": round(sb_val, 5) if sb_val is not None else None,
        "chikou_span": round(ck_val, 5) if ck_val is not None else None,
        "cloud_bias": cloud_color,
        "cloud_color": cloud_color,
        "price_vs_cloud": price_vs_cloud,
        "tk_cross": bool(tk_val > kj_val) if (tk_val and kj_val) else None,
    }


def detect_rsi_divergence(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    rsi: Optional[pd.Series] = None,
    lookback: int = 30,
) -> dict[str, Any]:
    """
    Detect regular bullish and bearish RSI divergences:
    - Regular Bullish: Price Lower Low, RSI Higher Low (reversal up signal)
    - Regular Bearish: Price Higher High, RSI Lower High (reversal down signal)
    """
    if rsi is None:
        try:
            rsi = ta.momentum.rsi(close=close, window=14)
        except Exception:
            return {"divergence": "none", "strength": 0.0, "details": "RSI computation failed"}

    if len(close) < 20 or len(rsi) < 20:
        return {"divergence": "none", "strength": 0.0, "details": "Insufficient data"}

    sub_low = low.iloc[-lookback:]
    sub_high = high.iloc[-lookback:]
    sub_rsi = rsi.iloc[-lookback:]

    bullish_div = False
    bearish_div = False
    details = []

    try:
        min_idx_1 = sub_low.iloc[-10:].idxmin()
        min_idx_2 = sub_low.iloc[:-10].idxmin()

        price_low_1 = float(sub_low.loc[min_idx_1])
        price_low_2 = float(sub_low.loc[min_idx_2])
        rsi_low_1 = float(sub_rsi.loc[min_idx_1])
        rsi_low_2 = float(sub_rsi.loc[min_idx_2])

        if price_low_1 < price_low_2 and rsi_low_1 > rsi_low_2 and rsi_low_1 < 50:
            bullish_div = True
            details.append(
                f"Bullish Divergence: Price Lower Low ({price_low_2:.5f} -> {price_low_1:.5f}) with RSI Higher Low ({rsi_low_2:.1f} -> {rsi_low_1:.1f})"
            )
    except Exception:
        pass

    try:
        max_idx_1 = sub_high.iloc[-10:].idxmax()
        max_idx_2 = sub_high.iloc[:-10].idxmax()

        price_high_1 = float(sub_high.loc[max_idx_1])
        price_high_2 = float(sub_high.loc[max_idx_2])
        rsi_high_1 = float(sub_rsi.loc[max_idx_1])
        rsi_high_2 = float(sub_rsi.loc[max_idx_2])

        if price_high_1 > price_high_2 and rsi_high_1 < rsi_high_2 and rsi_high_1 > 50:
            bearish_div = True
            details.append(
                f"Bearish Divergence: Price Higher High ({price_high_2:.5f} -> {price_high_1:.5f}) with RSI Lower High ({rsi_high_2:.1f} -> {rsi_high_1:.1f})"
            )
    except Exception:
        pass

    if bullish_div and not bearish_div:
        return {"divergence": "bullish", "strength": 0.8, "details": "; ".join(details)}
    elif bearish_div and not bullish_div:
        return {"divergence": "bearish", "strength": 0.8, "details": "; ".join(details)}
    elif bullish_div and bearish_div:
        return {"divergence": "mixed", "strength": 0.5, "details": "; ".join(details)}

    return {"divergence": "none", "strength": 0.0, "details": "No divergence detected across lookback window"}


def detect_macd_divergence(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    macd_line: Optional[pd.Series] = None,
    macd_hist: Optional[pd.Series] = None,
    lookback: int = 30,
) -> dict[str, Any]:
    """
    Detect regular and hidden MACD divergences (Line and Histogram):
    - Regular Bullish: Price Lower Low, MACD Higher Low (reversal up signal)
    - Regular Bearish: Price Higher High, MACD Lower High (reversal down signal)
    - Hidden Bullish: Price Higher Low, MACD Lower Low (continuation up signal)
    - Hidden Bearish: Price Lower High, MACD Higher High (continuation down signal)
    """
    if macd_line is None:
        try:
            m_calc = ta.trend.MACD(close=close)
            macd_line = m_calc.macd()
            if macd_hist is None:
                macd_hist = m_calc.macd_diff()
        except Exception:
            return {"divergence": "none", "type": "none", "strength": 0.0, "details": "MACD computation failed"}

    if len(close) < 20 or len(macd_line) < 20:
        return {"divergence": "none", "type": "none", "strength": 0.0, "details": "Insufficient data"}

    sub_low = low.iloc[-lookback:]
    sub_high = high.iloc[-lookback:]
    sub_macd = macd_line.iloc[-lookback:]

    bullish_div = False
    bearish_div = False
    hidden_bull = False
    hidden_bear = False
    details = []

    try:
        min_idx_1 = sub_low.iloc[-10:].idxmin()
        min_idx_2 = sub_low.iloc[:-10].idxmin()

        price_low_1 = float(sub_low.loc[min_idx_1])
        price_low_2 = float(sub_low.loc[min_idx_2])
        macd_low_1 = float(sub_macd.loc[min_idx_1])
        macd_low_2 = float(sub_macd.loc[min_idx_2])

        if price_low_1 < price_low_2 and macd_low_1 > macd_low_2:
            bullish_div = True
            details.append(
                f"Regular Bullish MACD Divergence: Price Lower Low ({price_low_2:.5f} -> {price_low_1:.5f}) with MACD Higher Low ({macd_low_2:.5f} -> {macd_low_1:.5f})"
            )
        elif price_low_1 > price_low_2 and macd_low_1 < macd_low_2:
            hidden_bull = True
            details.append(
                f"Hidden Bullish MACD Divergence: Price Higher Low ({price_low_2:.5f} -> {price_low_1:.5f}) with MACD Lower Low ({macd_low_2:.5f} -> {macd_low_1:.5f})"
            )
    except Exception:
        pass

    try:
        max_idx_1 = sub_high.iloc[-10:].idxmax()
        max_idx_2 = sub_high.iloc[:-10].idxmax()

        price_high_1 = float(sub_high.loc[max_idx_1])
        price_high_2 = float(sub_high.loc[max_idx_2])
        macd_high_1 = float(sub_macd.loc[max_idx_1])
        macd_high_2 = float(sub_macd.loc[max_idx_2])

        if price_high_1 > price_high_2 and macd_high_1 < macd_high_2:
            bearish_div = True
            details.append(
                f"Regular Bearish MACD Divergence: Price Higher High ({price_high_2:.5f} -> {price_high_1:.5f}) with MACD Lower High ({macd_high_2:.5f} -> {macd_high_1:.5f})"
            )
        elif price_high_1 < price_high_2 and macd_high_1 > macd_high_2:
            hidden_bear = True
            details.append(
                f"Hidden Bearish MACD Divergence: Price Lower High ({price_high_2:.5f} -> {price_high_1:.5f}) with MACD Higher High ({macd_high_2:.5f} -> {macd_high_1:.5f})"
            )
    except Exception:
        pass

    if bullish_div:
        return {"divergence": "bullish", "type": "regular", "strength": 0.85, "details": "; ".join(details)}
    elif bearish_div:
        return {"divergence": "bearish", "type": "regular", "strength": 0.85, "details": "; ".join(details)}
    elif hidden_bull:
        return {"divergence": "bullish", "type": "hidden", "strength": 0.75, "details": "; ".join(details)}
    elif hidden_bear:
        return {"divergence": "bearish", "type": "hidden", "strength": 0.75, "details": "; ".join(details)}

    return {
        "divergence": "none",
        "type": "none",
        "strength": 0.0,
        "details": "No MACD divergence detected across lookback window",
    }


# ------------------------------------------------------------------
# Pure Domain TechnicalIndicatorCalculator Class
# ------------------------------------------------------------------

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
        """
        if df is None or len(df) == 0:
            return {}

        required_cols = ("open", "high", "low", "close", "volume")
        if not all(col in df.columns for col in required_cols):
            return {}

        if not is_final and len(df) > 1:
            df = df.iloc[:-1].copy()

        result: dict[datetime, list[dict[str, Any]]] = {}

        def add(ts: Any, name: str, value: Any) -> None:
            if ts not in result:
                result[ts] = []
            result[ts].append({"name": name, "value_json": json.dumps(value)})

        close = pd.Series(df["close"])
        high = pd.Series(df["high"])
        low = pd.Series(df["low"])

        target_index = df.index[-100:] if len(df) > 100 else df.index

        # 1. Moving Averages
        for period in self.ma_periods:
            sma = ta.trend.sma_indicator(close, window=period, fillna=False)
            ema = ta.trend.ema_indicator(close, window=period, fillna=False)
            for ts in target_index:
                sma_v = sma.get(ts)
                ema_v = ema.get(ts)
                if sma_v is not None and pd.notna(sma_v):
                    add(ts, f"SMA_{period}", round(float(sma_v), 5))
                if ema_v is not None and pd.notna(ema_v):
                    add(ts, f"EMA_{period}", round(float(ema_v), 5))

        # 2. RSI
        rsi_series = ta.momentum.rsi(close, window=self.rsi_period, fillna=False)
        for ts in target_index:
            v = rsi_series.get(ts)
            if v is not None and pd.notna(v):
                add(ts, f"RSI_{self.rsi_period}", round(float(v), 2))

        # 3. MACD
        macd_obj = ta.trend.MACD(
            close,
            window_fast=self.macd_fast,
            window_slow=self.macd_slow,
            window_sign=self.macd_signal,
            fillna=False,
        )
        macd_line = macd_obj.macd()
        signal_line = macd_obj.macd_signal()
        hist = macd_obj.macd_diff()

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

        # 4. Bollinger Bands
        bb_obj = ta.volatility.BollingerBands(
            close,
            window=self.bb_period,
            window_dev=int(self.bb_std),
            fillna=False,
        )
        bb_upper = bb_obj.bollinger_hband()
        bb_mid = bb_obj.bollinger_mavg()
        bb_lower = bb_obj.bollinger_lband()
        bb_pct = bb_obj.bollinger_pband()
        bb_width = bb_obj.bollinger_wband()

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

        # 5. Stochastic
        stoch_obj = ta.momentum.StochasticOscillator(
            high,
            low,
            close,
            window=self.stoch_k,
            smooth_window=self.stoch_d,
            fillna=False,
        )
        stoch_k_series = stoch_obj.stoch()
        stoch_d_series = stoch_obj.stoch_signal()

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
                obv_series = ta.volume.on_balance_volume(close, volume, fillna=False)
                for ts in target_index:
                    v = obv_series.get(ts)
                    if v is not None and pd.notna(v):
                        add(ts, "OBV", round(float(v), 2))
        except Exception as e:
            logger.debug(f"OBV computation failed: {e}")

        # 6. ATR
        try:
            atr_series = ta.volatility.average_true_range(high, low, close, window=self.atr_period, fillna=False)
            for ts in target_index:
                v = atr_series.get(ts)
                if v is not None and pd.notna(v):
                    add(ts, f"ATR_{self.atr_period}", round(float(v), 5))
        except Exception as e:
            logger.debug(f"ATR computation failed: {e}")

        # 7. ADX
        try:
            adx_indicator = ta.trend.ADXIndicator(high, low, close, window=self.adx_period, fillna=False)
            adx_series = adx_indicator.adx()
            adx_pos = adx_indicator.adx_pos()
            adx_neg = adx_indicator.adx_neg()
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


# ------------------------------------------------------------------
# Canonical Chart Workspace Presets & Schema Normalizer
# ------------------------------------------------------------------

CHART_WORKSPACE_PRESETS: dict[str, dict[str, Any]] = {
    "smc_institutional": {
        "preset_id": "smc_institutional",
        "timeframe": "H4",
        "vision_sync_enabled": True,
        "overlays": {
            "ema": {"enabled": True, "periods": [20, 50, 200]},
            "sma": {"enabled": False, "periods": [20, 50]},
            "wma": {"enabled": False, "periods": [20]},
            "bollinger": {"enabled": False, "period": 20, "std_dev": 2.0},
            "keltner": {"enabled": False, "window": 20, "window_atr": 10, "multiplier": 2.0},
            "donchian": {"enabled": False, "window": 20},
            "vwap": {"enabled": True, "window": None},
            "supertrend": {"enabled": False, "period": 10, "multiplier": 3.0},
            "ichimoku": {"enabled": False, "tenkan": 9, "kijun": 26, "senkou_b": 52},
            "pivot_points": {"enabled": False, "method": "classic"},
            "smc_order_blocks": True,
            "smc_fvg": True,
            "smc_bos": True,
            "smc_liquidity": True,
            "volume_profile": True,
            "timesfm_cone": True,
            "show_positions": True,
            "show_ai_proposals": True,
        },
        "oscillators": {
            "volume": {"enabled": True, "ma_period": 20},
            "rsi": {"enabled": True, "period": 14, "overbought": 70.0, "oversold": 30.0},
            "macd": {"enabled": False, "fast": 12, "slow": 26, "signal": 9},
            "stochastic": {"enabled": False, "k_period": 14, "d_period": 3},
            "adx": {"enabled": False, "period": 14},
            "atr": {"enabled": False, "period": 14},
            "cvd_volatility": {"enabled": False, "mode": "cvd", "window": 20},
        },
    },
    "trend_momentum": {
        "preset_id": "trend_momentum",
        "timeframe": "H4",
        "vision_sync_enabled": True,
        "overlays": {
            "ema": {"enabled": True, "periods": [9, 21, 50, 200]},
            "sma": {"enabled": False, "periods": [20, 50]},
            "wma": {"enabled": False, "periods": [20]},
            "bollinger": {"enabled": False, "period": 20, "std_dev": 2.0},
            "keltner": {"enabled": False, "window": 20, "window_atr": 10, "multiplier": 2.0},
            "donchian": {"enabled": False, "window": 20},
            "vwap": {"enabled": False, "window": None},
            "supertrend": {"enabled": True, "period": 10, "multiplier": 3.0},
            "ichimoku": {"enabled": True, "tenkan": 9, "kijun": 26, "senkou_b": 52},
            "pivot_points": {"enabled": False, "method": "classic"},
            "smc_order_blocks": False,
            "smc_fvg": False,
            "smc_bos": True,
            "smc_liquidity": False,
            "volume_profile": False,
            "timesfm_cone": False,
            "show_positions": True,
            "show_ai_proposals": True,
        },
        "oscillators": {
            "volume": {"enabled": True, "ma_period": 20},
            "rsi": {"enabled": False, "period": 14, "overbought": 70.0, "oversold": 30.0},
            "macd": {"enabled": True, "fast": 12, "slow": 26, "signal": 9},
            "stochastic": {"enabled": False, "k_period": 14, "d_period": 3},
            "adx": {"enabled": True, "period": 14},
            "atr": {"enabled": False, "period": 14},
            "cvd_volatility": {"enabled": False, "mode": "cvd", "window": 20},
        },
    },
    "volatility_reversion": {
        "preset_id": "volatility_reversion",
        "timeframe": "H4",
        "vision_sync_enabled": True,
        "overlays": {
            "ema": {"enabled": False, "periods": [20, 50, 200]},
            "sma": {"enabled": False, "periods": [20, 50]},
            "wma": {"enabled": False, "periods": [20]},
            "bollinger": {"enabled": True, "period": 20, "std_dev": 2.0},
            "keltner": {"enabled": True, "window": 20, "window_atr": 10, "multiplier": 2.0},
            "donchian": {"enabled": False, "window": 20},
            "vwap": {"enabled": True, "window": None},
            "supertrend": {"enabled": False, "period": 10, "multiplier": 3.0},
            "ichimoku": {"enabled": False, "tenkan": 9, "kijun": 26, "senkou_b": 52},
            "pivot_points": {"enabled": True, "method": "fibonacci"},
            "smc_order_blocks": False,
            "smc_fvg": False,
            "smc_bos": False,
            "smc_liquidity": False,
            "volume_profile": False,
            "timesfm_cone": False,
            "show_positions": True,
            "show_ai_proposals": True,
        },
        "oscillators": {
            "volume": {"enabled": True, "ma_period": 20},
            "rsi": {"enabled": True, "period": 14, "overbought": 70.0, "oversold": 30.0},
            "macd": {"enabled": False, "fast": 12, "slow": 26, "signal": 9},
            "stochastic": {"enabled": True, "k_period": 14, "d_period": 3},
            "adx": {"enabled": False, "period": 14},
            "atr": {"enabled": True, "period": 14},
            "cvd_volatility": {"enabled": False, "mode": "cvd", "window": 20},
        },
    },
    "quant_orderflow": {
        "preset_id": "quant_orderflow",
        "timeframe": "H4",
        "vision_sync_enabled": True,
        "overlays": {
            "ema": {"enabled": True, "periods": [20, 50]},
            "sma": {"enabled": False, "periods": [20, 50]},
            "wma": {"enabled": False, "periods": [20]},
            "bollinger": {"enabled": False, "period": 20, "std_dev": 2.0},
            "keltner": {"enabled": False, "window": 20, "window_atr": 10, "multiplier": 2.0},
            "donchian": {"enabled": False, "window": 20},
            "vwap": {"enabled": True, "window": None},
            "supertrend": {"enabled": False, "period": 10, "multiplier": 3.0},
            "ichimoku": {"enabled": False, "tenkan": 9, "kijun": 26, "senkou_b": 52},
            "pivot_points": {"enabled": False, "method": "classic"},
            "smc_order_blocks": True,
            "smc_fvg": True,
            "smc_bos": False,
            "smc_liquidity": True,
            "volume_profile": True,
            "timesfm_cone": True,
            "show_positions": True,
            "show_ai_proposals": True,
        },
        "oscillators": {
            "volume": {"enabled": True, "ma_period": 20},
            "rsi": {"enabled": True, "period": 14, "overbought": 70.0, "oversold": 30.0},
            "macd": {"enabled": False, "fast": 12, "slow": 26, "signal": 9},
            "stochastic": {"enabled": False, "k_period": 14, "d_period": 3},
            "adx": {"enabled": False, "period": 14},
            "atr": {"enabled": False, "period": 14},
            "cvd_volatility": {"enabled": True, "mode": "cvd", "window": 20},
        },
    },
}

DEFAULT_CHART_WORKSPACE_CONFIG: dict[str, Any] = CHART_WORKSPACE_PRESETS["smc_institutional"]


def _clamp_int(val: Any, low: int = 2, high: int = 500, default: int = 20) -> int:
    """Clamps an integer within [low, high] with default fallback."""
    try:
        iv = int(val)
        return max(low, min(high, iv))
    except ValueError, TypeError:
        return default


def _clamp_float(val: Any, low: float = 0.1, high: float = 20.0, default: float = 2.0) -> float:
    """Clamps a float within [low, high] with default fallback."""
    try:
        fv = float(val)
        return max(low, min(high, fv))
    except ValueError, TypeError:
        return default


def normalize_chart_workspace_config(raw: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Safely normalizes and deep-merges raw workspace configuration against canonical presets.
    Clamps periods (2..500) and multipliers (0.1..20.0) so invalid user inputs never crash calculations.
    """
    if raw is None or not isinstance(raw, dict):
        return copy.deepcopy(DEFAULT_CHART_WORKSPACE_CONFIG)

    preset_id = str(raw.get("preset_id", "smc_institutional")).lower()
    base_template = CHART_WORKSPACE_PRESETS.get(preset_id, DEFAULT_CHART_WORKSPACE_CONFIG)
    config = copy.deepcopy(base_template)

    if "timeframe" in raw and isinstance(raw["timeframe"], str) and raw["timeframe"].strip():
        config["timeframe"] = raw["timeframe"].strip().upper()
    if "vision_sync_enabled" in raw:
        config["vision_sync_enabled"] = bool(raw["vision_sync_enabled"])

    raw_overlays = raw.get("overlays")
    if isinstance(raw_overlays, dict):
        for key, val in raw_overlays.items():
            if key in (
                "smc_order_blocks",
                "smc_fvg",
                "smc_bos",
                "smc_liquidity",
                "volume_profile",
                "timesfm_cone",
                "show_positions",
                "show_ai_proposals",
            ):
                config["overlays"][key] = bool(val)
            elif key in ("ema", "sma", "wma") and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "periods" in val and isinstance(val["periods"], (list, tuple)):
                    clamped_periods = sorted(
                        {_clamp_int(p, 2, 500, 20) for p in val["periods"] if isinstance(p, (int, float, str))}
                    )
                    if clamped_periods:
                        cur["periods"] = clamped_periods
            elif key == "bollinger" and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "period" in val:
                    cur["period"] = _clamp_int(val["period"], 2, 500, 20)
                if "std_dev" in val:
                    cur["std_dev"] = _clamp_float(val["std_dev"], 0.1, 10.0, 2.0)
            elif key == "keltner" and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "window" in val:
                    cur["window"] = _clamp_int(val["window"], 2, 500, 20)
                if "window_atr" in val:
                    cur["window_atr"] = _clamp_int(val["window_atr"], 2, 500, 10)
                if "multiplier" in val:
                    cur["multiplier"] = _clamp_float(val["multiplier"], 0.1, 10.0, 2.0)
            elif key == "donchian" and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "window" in val:
                    cur["window"] = _clamp_int(val["window"], 2, 500, 20)
            elif key == "vwap" and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "window" in val:
                    cur["window"] = _clamp_int(val["window"], 2, 500, 20) if val["window"] is not None else None
            elif key == "supertrend" and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "period" in val:
                    cur["period"] = _clamp_int(val["period"], 2, 500, 10)
                if "multiplier" in val:
                    cur["multiplier"] = _clamp_float(val["multiplier"], 0.1, 20.0, 3.0)
            elif key == "ichimoku" and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "tenkan" in val:
                    cur["tenkan"] = _clamp_int(val["tenkan"], 2, 500, 9)
                if "kijun" in val:
                    cur["kijun"] = _clamp_int(val["kijun"], 2, 500, 26)
                if "senkou_b" in val:
                    cur["senkou_b"] = _clamp_int(val["senkou_b"], 2, 500, 52)
            elif key == "pivot_points" and isinstance(val, dict):
                cur = config["overlays"].setdefault(key, {})
                if "enabled" in val:
                    cur["enabled"] = bool(val["enabled"])
                if "method" in val and str(val["method"]).lower() in (
                    "classic",
                    "fibonacci",
                    "camarilla",
                    "woodie",
                    "all",
                ):
                    cur["method"] = str(val["method"]).lower()

    raw_oscillators = raw.get("oscillators")
    if isinstance(raw_oscillators, dict):
        for key, val in raw_oscillators.items():
            if not isinstance(val, dict):
                continue
            cur = config["oscillators"].setdefault(key, {})
            if "enabled" in val:
                cur["enabled"] = bool(val["enabled"])
            if key == "volume":
                if "ma_period" in val:
                    cur["ma_period"] = _clamp_int(val["ma_period"], 2, 500, 20)
            elif key == "rsi":
                if "period" in val:
                    cur["period"] = _clamp_int(val["period"], 2, 500, 14)
                if "overbought" in val:
                    cur["overbought"] = _clamp_float(val["overbought"], 50.0, 95.0, 70.0)
                if "oversold" in val:
                    cur["oversold"] = _clamp_float(val["oversold"], 5.0, 50.0, 30.0)
            elif key == "macd":
                if "fast" in val:
                    cur["fast"] = _clamp_int(val["fast"], 2, 500, 12)
                if "slow" in val:
                    cur["slow"] = _clamp_int(val["slow"], 2, 500, 26)
                if "signal" in val:
                    cur["signal"] = _clamp_int(val["signal"], 1, 500, 9)
                if cur.get("fast", 12) >= cur.get("slow", 26):
                    cur["slow"] = cur.get("fast", 12) + 1
            elif key == "stochastic":
                if "k_period" in val:
                    cur["k_period"] = _clamp_int(val["k_period"], 2, 500, 14)
                if "d_period" in val:
                    cur["d_period"] = _clamp_int(val["d_period"], 1, 100, 3)
            elif key in ("adx", "atr"):
                if "period" in val:
                    cur["period"] = _clamp_int(val["period"], 2, 500, 14)
            elif key == "cvd_volatility":
                if "mode" in val and str(val["mode"]).lower() in ("cvd", "yz_vol", "yang_zhang", "ac1"):
                    m_val = str(val["mode"]).lower()
                    cur["mode"] = "yz_vol" if m_val == "yang_zhang" else m_val
                if "window" in val:
                    cur["window"] = _clamp_int(val["window"], 2, 500, 20)

    return config


# ------------------------------------------------------------------
# Pure Vectorized Time-Series Indicator Functions
# ------------------------------------------------------------------


def compute_wma(close: pd.Series, period: int = 20) -> pd.Series:
    """Computes Weighted Moving Average (WMA) for specified period."""
    if close is None or len(close) == 0:
        return pd.Series(dtype=float)
    p = max(2, min(500, int(period)))
    if len(close) < p:
        return pd.Series(np.nan, index=close.index, dtype=float)

    weights = np.arange(1, p + 1, dtype=float)
    w_sum = weights.sum()
    if w_sum <= 0:
        return pd.Series(np.nan, index=close.index, dtype=float)
    w = weights / w_sum

    res = close.astype(float).rolling(p).apply(lambda s: float(np.dot(s, w)), raw=True)
    return pd.Series(res, index=close.index, dtype=float)


def compute_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    window: Optional[int] = None,
) -> pd.Series:
    """
    Computes Volume-Weighted Average Price (VWAP).
    If window is given, computes rolling VWAP.
    Otherwise anchors by session/day if DatetimeIndex, or cumulative across series.
    If volume is all zeros or missing, falls back to rolling/cumulative mean of typical price.
    """
    if close is None or len(close) == 0:
        return pd.Series(dtype=float)

    h = high.astype(float) if high is not None else close.astype(float)
    l = low.astype(float) if low is not None else close.astype(float)
    c = close.astype(float)
    tp = (h + l + c) / 3.0

    vol = (
        volume.astype(float).fillna(0.0)
        if volume is not None and len(volume) == len(close)
        else pd.Series(0.0, index=close.index)
    )
    has_vol = bool((vol > 0).any())

    if window is not None and int(window) > 1:
        w = int(window)
        if has_vol:
            pv = tp * vol
            cum_pv = pd.Series(pv.rolling(w).sum())
            cum_vol = pd.Series(vol.rolling(w).sum())
            fallback_tp = pd.Series(tp.rolling(w).mean())
            vwap = np.where(cum_vol > 1e-12, cum_pv / np.maximum(cum_vol, 1e-12), fallback_tp)
            return pd.Series(vwap, index=close.index, dtype=float).fillna(tp)
        else:
            return pd.Series(tp.rolling(w).mean(), index=close.index, dtype=float).fillna(tp)

    # Session/daily anchor if DatetimeIndex has multiple dates
    if isinstance(close.index, pd.DatetimeIndex):
        date_labels = [str(ts)[:10] for ts in close.index]
        if len(set(date_labels)) > 1:
            dates = pd.Index(date_labels)
            if has_vol:
                pv = tp * vol
                cum_pv = pv.groupby(dates).cumsum()
                cum_vol = vol.groupby(dates).cumsum()
                fallback_tp = tp.groupby(dates).expanding().mean().reset_index(level=0, drop=True)
                vwap = np.where(cum_vol > 1e-12, cum_pv / np.maximum(cum_vol, 1e-12), fallback_tp)
                return pd.Series(vwap, index=close.index, dtype=float).fillna(tp)
            else:
                return pd.Series(
                    tp.groupby(dates).expanding().mean().reset_index(level=0, drop=True),
                    index=close.index,
                    dtype=float,
                ).fillna(tp)

    # Cumulative overall
    if has_vol:
        pv = tp * vol
        cum_pv = pv.cumsum()
        cum_vol = vol.cumsum()
        fallback_tp = tp.expanding().mean()
        vwap = np.where(cum_vol > 1e-12, cum_pv / np.maximum(cum_vol, 1e-12), fallback_tp)
        return pd.Series(vwap, index=close.index, dtype=float).fillna(tp)
    else:
        return pd.Series(tp.expanding().mean(), index=close.index, dtype=float).fillna(tp)


def compute_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.Series, pd.Series]:
    """
    Computes Supertrend indicator and trend direction.
    Returns:
        (supertrend_series, direction_series)
        where direction is 1 (bullish) or -1 (bearish).
    """
    if close is None or len(close) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=int)

    p = max(2, min(500, int(period)))
    mult = max(0.1, min(20.0, float(multiplier)))

    if len(close) < p:
        return pd.Series(np.nan, index=close.index, dtype=float), pd.Series(1, index=close.index, dtype=int)

    atr = compute_atr(high, low, close, period=p)
    hl2 = (high.astype(float) + low.astype(float)) / 2.0

    basic_upper = hl2 + (mult * atr)
    basic_lower = hl2 - (mult * atr)

    n = len(close)
    c_arr = close.astype(float).to_numpy()
    bu_arr = basic_upper.to_numpy()
    bl_arr = basic_lower.to_numpy()

    final_upper = np.zeros(n, dtype=float)
    final_lower = np.zeros(n, dtype=float)
    supertrend = np.zeros(n, dtype=float)
    direction = np.zeros(n, dtype=int)

    start_idx = p - 1
    final_upper[:start_idx] = np.nan
    final_lower[:start_idx] = np.nan
    supertrend[:start_idx] = np.nan
    direction[:start_idx] = 1

    final_upper[start_idx] = bu_arr[start_idx]
    final_lower[start_idx] = bl_arr[start_idx]
    if c_arr[start_idx] <= final_upper[start_idx]:
        supertrend[start_idx] = final_upper[start_idx]
        direction[start_idx] = -1
    else:
        supertrend[start_idx] = final_lower[start_idx]
        direction[start_idx] = 1

    for i in range(start_idx + 1, n):
        # Upper band
        if bu_arr[i] < final_upper[i - 1] or c_arr[i - 1] > final_upper[i - 1]:
            final_upper[i] = bu_arr[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Lower band
        if bl_arr[i] > final_lower[i - 1] or c_arr[i - 1] < final_lower[i - 1]:
            final_lower[i] = bl_arr[i]
        else:
            final_lower[i] = final_lower[i - 1]

        prev_st = supertrend[i - 1]
        prev_fu = final_upper[i - 1]

        if prev_st == prev_fu:
            if c_arr[i] <= final_upper[i]:
                supertrend[i] = final_upper[i]
                direction[i] = -1
            else:
                supertrend[i] = final_lower[i]
                direction[i] = 1
        else:
            if c_arr[i] >= final_lower[i]:
                supertrend[i] = final_lower[i]
                direction[i] = 1
            else:
                supertrend[i] = final_upper[i]
                direction[i] = -1

    return pd.Series(supertrend, index=close.index, dtype=float), pd.Series(direction, index=close.index, dtype=int)


def compute_keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
    window_atr: int = 10,
    multiplier: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Computes Keltner Channels: upper, middle, lower."""
    w = max(2, min(500, int(window)))
    w_atr = max(2, min(500, int(window_atr)))
    mult = max(0.1, min(20.0, float(multiplier)))

    mid = pd.Series(ta.trend.ema_indicator(close, window=w, fillna=False), index=close.index)
    atr = compute_atr(high, low, close, period=w_atr)
    upper = mid + (mult * atr)
    lower = mid - (mult * atr)
    return upper, mid, lower


def compute_donchian_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Computes Donchian Channels: upper, middle, lower."""
    w = max(2, min(500, int(window)))
    upper = pd.Series(high.astype(float).rolling(w).max(), index=close.index)
    lower = pd.Series(low.astype(float).rolling(w).min(), index=close.index)
    mid = (upper + lower) / 2.0
    return upper, mid, lower


def compute_ichimoku_series(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
) -> dict[str, pd.Series]:
    """
    Computes Ichimoku Kinko Hyo full series:
    - tenkan_sen
    - kijun_sen
    - senkou_span_a
    - senkou_span_b
    - chikou_span
    """
    tk_p = max(2, min(500, int(tenkan_period)))
    kj_p = max(2, min(500, int(kijun_period)))
    sb_p = max(2, min(500, int(senkou_b_period)))

    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)

    tenkan = (pd.Series(h.rolling(tk_p).max()) + pd.Series(l.rolling(tk_p).min())) / 2.0
    kijun = (pd.Series(h.rolling(kj_p).max()) + pd.Series(l.rolling(kj_p).min())) / 2.0
    senkou_a = pd.Series((tenkan + kijun) / 2.0).shift(kj_p)
    senkou_b = pd.Series((pd.Series(h.rolling(sb_p).max()) + pd.Series(l.rolling(sb_p).min())) / 2.0).shift(kj_p)
    chikou = c.shift(-kj_p)

    return {
        "tenkan_sen": pd.Series(tenkan, index=close.index),
        "kijun_sen": pd.Series(kijun, index=close.index),
        "senkou_span_a": pd.Series(senkou_a, index=close.index),
        "senkou_span_b": pd.Series(senkou_b, index=close.index),
        "chikou_span": pd.Series(chikou, index=close.index),
    }


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Computes On-Balance Volume (OBV)."""
    if close is None or len(close) == 0:
        return pd.Series(dtype=float)
    if volume is None or len(volume) == 0 or not (volume > 0).any():
        return pd.Series(0.0, index=close.index, dtype=float)
    return pd.Series(ta.volume.on_balance_volume(close, volume, fillna=False), index=close.index).fillna(0.0)


def compute_cvd_series(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """
    Computes Cumulative Volume Delta (CVD) series from intrabar buying/selling pressure.
    delta = np.where((high - low) > 1e-12, volume * ((close - low) - (high - close)) / (high - low), np.where(close >= open_, volume, -volume))
    """
    if close is None or len(close) == 0:
        return pd.Series(dtype=float)

    o = open_.astype(float) if open_ is not None else close.astype(float)
    h = high.astype(float) if high is not None else close.astype(float)
    l = low.astype(float) if low is not None else close.astype(float)
    c = close.astype(float)
    v = (
        volume.astype(float).fillna(0.0)
        if volume is not None and len(volume) == len(close)
        else pd.Series(0.0, index=close.index)
    )

    hl_diff = h - l
    delta = np.where(
        hl_diff > 1e-12,
        v * ((c - l) - (h - c)) / np.maximum(hl_diff, 1e-12),
        np.where(c >= o, v, -v),
    )
    return pd.Series(delta, index=close.index).cumsum()


# ------------------------------------------------------------------
# Workspace Evaluation Engine
# ------------------------------------------------------------------


def _extract_unix_timestamps(df: pd.DataFrame) -> list[int]:
    """Extract integer unix timestamps from DataFrame."""
    if isinstance(df.index, pd.DatetimeIndex):
        return [int(ts.timestamp()) for ts in df.index]

    for col in ("timestamp", "time", "date", "Date", "Timestamp", "Time"):
        if col in df.columns:
            series = df[col]
            sample = series.iloc[0] if len(series) > 0 else None
            if isinstance(sample, (int, np.integer)):
                if sample > 1e11:
                    return [int(v // 1000) for v in series]
                return [int(v) for v in series]
            elif isinstance(sample, (float, np.floating)):
                if sample > 1e11:
                    return [int(v // 1000) for v in series]
                return [int(v) for v in series]
            else:
                try:
                    dt_series = pd.to_datetime(series)
                    return [int(ts.timestamp()) for ts in dt_series]
                except Exception:
                    pass

    now_ts = int(datetime.now(timezone.utc).timestamp())
    step = 3600
    start = now_ts - (len(df) * step)
    return [start + (i * step) for i in range(len(df))]


def evaluate_workspace_indicators(
    df: pd.DataFrame,
    workspace_config: Optional[dict[str, Any]] = None,
    max_bars: int = 250,
) -> dict[str, Any]:
    """
    Evaluates all active indicators in the workspace configuration on OHLCV data.
    Computes over the full series for indicator warm-up, then slices output arrays
    to the last max_bars.
    Returns:
        {
            "workspace_config": dict,
            "series": dict[str, list[dict]],
            "pivot_points": Optional[dict],
            "summary": dict[str, dict],
            "overall": dict[str, Any],
            "declared_figures": dict[str, float],
        }
    """
    cfg = normalize_chart_workspace_config(workspace_config)
    empty_result: dict[str, Any] = {
        "workspace_config": cfg,
        "series": {},
        "pivot_points": None,
        "summary": {},
        "overall": {
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "total_directional": 0,
            "bias": "neutral",
            "alignment_ratio": 0.0,
            "alignment_pct": 0.0,
            "confluence_adjustment": 0,
        },
        "declared_figures": {},
    }

    if df is None or len(df) == 0:
        return empty_result

    col_map: dict[str, str] = {}
    for col in df.columns:
        c_low = str(col).lower()
        if c_low in ["open", "high", "low", "close", "volume"]:
            col_map[col] = c_low
        elif c_low in ["vol", "tick_volume"]:
            col_map[col] = "volume"

    work_df = df.rename(columns=col_map)
    for req in ("open", "high", "low", "close"):
        if req not in work_df.columns:
            return empty_result

    open_s = pd.Series(pd.to_numeric(work_df["open"], errors="coerce"), index=work_df.index)
    high_s = pd.Series(pd.to_numeric(work_df["high"], errors="coerce"), index=work_df.index)
    low_s = pd.Series(pd.to_numeric(work_df["low"], errors="coerce"), index=work_df.index)
    close_s = pd.Series(pd.to_numeric(work_df["close"], errors="coerce"), index=work_df.index)

    if "volume" in work_df.columns:
        vol_s = pd.Series(pd.to_numeric(work_df["volume"], errors="coerce"), index=work_df.index).fillna(0.0)
    else:
        vol_s = pd.Series(0.0, index=work_df.index)

    timestamps = _extract_unix_timestamps(df)
    n_total = len(df)
    slice_len = min(n_total, max(1, max_bars))
    slice_start = n_total - slice_len
    target_idx = df.index[slice_start:]
    target_ts = timestamps[slice_start:]

    series_dict: dict[str, list[dict[str, Any]]] = {}
    summary_dict: dict[str, dict[str, Any]] = {}
    figures_dict: dict[str, float] = {}

    overlays = cfg.get("overlays", {})
    oscillators = cfg.get("oscillators", {})

    last_close = float(close_s.iloc[-1]) if pd.notna(close_s.iloc[-1]) else 0.0
    figures_dict["CLOSE"] = round(last_close, 5)

    def _pack_series(s: pd.Series) -> list[dict[str, Any]]:
        pts: list[dict[str, Any]] = []
        for t, idx in zip(target_ts, target_idx):
            v = s.get(idx)
            if v is not None and pd.notna(v) and np.isfinite(v):
                pts.append({"time": t, "value": round(float(v), 6)})
        return pts

    # 1. EMA Overlays
    ema_cfg = overlays.get("ema", {})
    if ema_cfg.get("enabled", False):
        for p in ema_cfg.get("periods", [20, 50, 200]):
            ema_s = ta.trend.ema_indicator(close_s, window=p, fillna=False)
            series_dict[f"ema_{p}"] = _pack_series(ema_s)
            val = float(ema_s.iloc[-1]) if pd.notna(ema_s.iloc[-1]) else None
            prev_val = float(ema_s.iloc[-2]) if len(ema_s) >= 2 and pd.notna(ema_s.iloc[-2]) else val
            if val is not None:
                figures_dict[f"EMA_{p}"] = round(val, 5)
                delta = round(val - prev_val, 6) if prev_val is not None else None
                slope = (
                    "rising"
                    if (delta is not None and delta > 1e-7)
                    else ("falling" if (delta is not None and delta < -1e-7) else "flat")
                )
                sig = "bullish" if last_close > val else ("bearish" if last_close < val else "neutral")
                summary_dict[f"EMA_{p}"] = {
                    "name": f"EMA {p}",
                    "category": "overlay",
                    "latest": round(val, 5),
                    "prev": round(prev_val, 5) if prev_val is not None else None,
                    "delta": delta,
                    "slope": slope,
                    "signal": sig,
                    "details": f"Price ({last_close:.5f}) {'above' if sig == 'bullish' else 'below'} EMA_{p} ({val:.5f}), slope is {slope}",
                }

    # 2. SMA Overlays
    sma_cfg = overlays.get("sma", {})
    if sma_cfg.get("enabled", False):
        for p in sma_cfg.get("periods", [20, 50]):
            sma_s = ta.trend.sma_indicator(close_s, window=p, fillna=False)
            series_dict[f"sma_{p}"] = _pack_series(sma_s)
            val = float(sma_s.iloc[-1]) if pd.notna(sma_s.iloc[-1]) else None
            prev_val = float(sma_s.iloc[-2]) if len(sma_s) >= 2 and pd.notna(sma_s.iloc[-2]) else val
            if val is not None:
                figures_dict[f"SMA_{p}"] = round(val, 5)
                delta = round(val - prev_val, 6) if prev_val is not None else None
                slope = (
                    "rising"
                    if (delta is not None and delta > 1e-7)
                    else ("falling" if (delta is not None and delta < -1e-7) else "flat")
                )
                sig = "bullish" if last_close > val else ("bearish" if last_close < val else "neutral")
                summary_dict[f"SMA_{p}"] = {
                    "name": f"SMA {p}",
                    "category": "overlay",
                    "latest": round(val, 5),
                    "prev": round(prev_val, 5) if prev_val is not None else None,
                    "delta": delta,
                    "slope": slope,
                    "signal": sig,
                    "details": f"Price ({last_close:.5f}) {'above' if sig == 'bullish' else 'below'} SMA_{p} ({val:.5f}), slope is {slope}",
                }

    # 3. WMA Overlays
    wma_cfg = overlays.get("wma", {})
    if wma_cfg.get("enabled", False):
        for p in wma_cfg.get("periods", [20]):
            wma_s = compute_wma(close_s, period=p)
            series_dict[f"wma_{p}"] = _pack_series(wma_s)
            val = float(wma_s.iloc[-1]) if pd.notna(wma_s.iloc[-1]) else None
            prev_val = float(wma_s.iloc[-2]) if len(wma_s) >= 2 and pd.notna(wma_s.iloc[-2]) else val
            if val is not None:
                figures_dict[f"WMA_{p}"] = round(val, 5)
                delta = round(val - prev_val, 6) if prev_val is not None else None
                slope = (
                    "rising"
                    if (delta is not None and delta > 1e-7)
                    else ("falling" if (delta is not None and delta < -1e-7) else "flat")
                )
                sig = "bullish" if last_close > val else ("bearish" if last_close < val else "neutral")
                summary_dict[f"WMA_{p}"] = {
                    "name": f"WMA {p}",
                    "category": "overlay",
                    "latest": round(val, 5),
                    "prev": round(prev_val, 5) if prev_val is not None else None,
                    "delta": delta,
                    "slope": slope,
                    "signal": sig,
                    "details": f"Price ({last_close:.5f}) {'above' if sig == 'bullish' else 'below'} WMA_{p} ({val:.5f}), slope is {slope}",
                }

    # 4. Bollinger Bands
    bb_cfg = overlays.get("bollinger", {})
    if bb_cfg.get("enabled", False):
        bb_u, bb_m, bb_l, bb_p, bb_w = compute_bollinger_bands(
            close_s, period=bb_cfg.get("period", 20), std_dev=bb_cfg.get("std_dev", 2.0)
        )
        series_dict["bb_upper"] = _pack_series(bb_u)
        series_dict["bb_mid"] = _pack_series(bb_m)
        series_dict["bb_lower"] = _pack_series(bb_l)
        u_val = float(bb_u.iloc[-1]) if pd.notna(bb_u.iloc[-1]) else None
        m_val = float(bb_m.iloc[-1]) if pd.notna(bb_m.iloc[-1]) else None
        l_val = float(bb_l.iloc[-1]) if pd.notna(bb_l.iloc[-1]) else None
        if u_val is not None and m_val is not None and l_val is not None:
            figures_dict["BB_UPPER"] = round(u_val, 5)
            figures_dict["BB_MID"] = round(m_val, 5)
            figures_dict["BB_LOWER"] = round(l_val, 5)
            prev_m = float(bb_m.iloc[-2]) if len(bb_m) >= 2 and pd.notna(bb_m.iloc[-2]) else m_val
            delta = round(m_val - prev_m, 6)
            slope = "rising" if delta > 1e-7 else ("falling" if delta < -1e-7 else "flat")
            sig = "bullish" if last_close > m_val else ("bearish" if last_close < m_val else "neutral")
            summary_dict["Bollinger_Bands"] = {
                "name": "Bollinger Bands",
                "category": "overlay",
                "latest": {"upper": round(u_val, 5), "mid": round(m_val, 5), "lower": round(l_val, 5)},
                "prev": round(prev_m, 5),
                "delta": delta,
                "slope": slope,
                "signal": sig,
                "details": f"Price ({last_close:.5f}) relative to Bollinger Mid ({m_val:.5f}) is {sig}",
            }

    # 5. Keltner Channels
    kc_cfg = overlays.get("keltner", {})
    if kc_cfg.get("enabled", False):
        kc_u, kc_m, kc_l = compute_keltner_channels(
            high_s,
            low_s,
            close_s,
            window=kc_cfg.get("window", 20),
            window_atr=kc_cfg.get("window_atr", 10),
            multiplier=kc_cfg.get("multiplier", 2.0),
        )
        series_dict["kc_upper"] = _pack_series(kc_u)
        series_dict["kc_mid"] = _pack_series(kc_m)
        series_dict["kc_lower"] = _pack_series(kc_l)
        u_val = float(kc_u.iloc[-1]) if pd.notna(kc_u.iloc[-1]) else None
        m_val = float(kc_m.iloc[-1]) if pd.notna(kc_m.iloc[-1]) else None
        l_val = float(kc_l.iloc[-1]) if pd.notna(kc_l.iloc[-1]) else None
        if u_val is not None and m_val is not None and l_val is not None:
            figures_dict["KC_UPPER"] = round(u_val, 5)
            figures_dict["KC_MID"] = round(m_val, 5)
            figures_dict["KC_LOWER"] = round(l_val, 5)
            sig = "bullish" if last_close > m_val else ("bearish" if last_close < m_val else "neutral")
            summary_dict["Keltner_Channels"] = {
                "name": "Keltner Channels",
                "category": "overlay",
                "latest": {"upper": round(u_val, 5), "mid": round(m_val, 5), "lower": round(l_val, 5)},
                "prev": None,
                "delta": None,
                "slope": "flat",
                "signal": sig,
                "details": f"Price ({last_close:.5f}) vs KC Mid ({m_val:.5f}) is {sig}",
            }

    # 6. Donchian Channels
    dc_cfg = overlays.get("donchian", {})
    if dc_cfg.get("enabled", False):
        dc_u, dc_m, dc_l = compute_donchian_channels(high_s, low_s, close_s, window=dc_cfg.get("window", 20))
        series_dict["dc_upper"] = _pack_series(dc_u)
        series_dict["dc_mid"] = _pack_series(dc_m)
        series_dict["dc_lower"] = _pack_series(dc_l)
        u_val = float(dc_u.iloc[-1]) if pd.notna(dc_u.iloc[-1]) else None
        m_val = float(dc_m.iloc[-1]) if pd.notna(dc_m.iloc[-1]) else None
        l_val = float(dc_l.iloc[-1]) if pd.notna(dc_l.iloc[-1]) else None
        if u_val is not None and m_val is not None and l_val is not None:
            figures_dict["DC_UPPER"] = round(u_val, 5)
            figures_dict["DC_MID"] = round(m_val, 5)
            figures_dict["DC_LOWER"] = round(l_val, 5)
            sig = "bullish" if last_close > m_val else ("bearish" if last_close < m_val else "neutral")
            summary_dict["Donchian_Channels"] = {
                "name": "Donchian Channels",
                "category": "overlay",
                "latest": {"upper": round(u_val, 5), "mid": round(m_val, 5), "lower": round(l_val, 5)},
                "prev": None,
                "delta": None,
                "slope": "flat",
                "signal": sig,
                "details": f"Price ({last_close:.5f}) vs DC Mid ({m_val:.5f}) is {sig}",
            }

    # 7. VWAP
    vwap_cfg = overlays.get("vwap", {})
    if vwap_cfg.get("enabled", False):
        vwap_s = compute_vwap(high_s, low_s, close_s, vol_s, window=vwap_cfg.get("window"))
        series_dict["vwap"] = _pack_series(vwap_s)
        val = float(vwap_s.iloc[-1]) if pd.notna(vwap_s.iloc[-1]) else None
        prev_val = float(vwap_s.iloc[-2]) if len(vwap_s) >= 2 and pd.notna(vwap_s.iloc[-2]) else val
        if val is not None:
            figures_dict["VWAP"] = round(val, 5)
            delta = round(val - prev_val, 6) if prev_val is not None else None
            slope = (
                "rising"
                if (delta is not None and delta > 1e-7)
                else ("falling" if (delta is not None and delta < -1e-7) else "flat")
            )
            sig = "bullish" if last_close > val else ("bearish" if last_close < val else "neutral")
            summary_dict["VWAP"] = {
                "name": "VWAP",
                "category": "overlay",
                "latest": round(val, 5),
                "prev": round(prev_val, 5) if prev_val is not None else None,
                "delta": delta,
                "slope": slope,
                "signal": sig,
                "details": f"Price ({last_close:.5f}) {'above' if sig == 'bullish' else 'below'} VWAP ({val:.5f})",
            }

    # 8. Supertrend
    st_cfg = overlays.get("supertrend", {})
    if st_cfg.get("enabled", False):
        st_s, st_dir = compute_supertrend(
            high_s,
            low_s,
            close_s,
            period=st_cfg.get("period", 10),
            multiplier=st_cfg.get("multiplier", 3.0),
        )
        st_pts: list[dict[str, Any]] = []
        for t, idx in zip(target_ts, target_idx):
            v = st_s.get(idx)
            d = st_dir.get(idx)
            if v is not None and pd.notna(v) and np.isfinite(v):
                dir_int = 1
                if d is not None:
                    try:
                        dir_int = int(d)
                    except ValueError, TypeError:
                        dir_int = 1
                st_pts.append({"time": t, "value": round(float(v), 6), "direction": dir_int})
        series_dict["supertrend"] = st_pts
        val = float(st_s.iloc[-1]) if pd.notna(st_s.iloc[-1]) else None
        dir_val = int(st_dir.iloc[-1]) if pd.notna(st_dir.iloc[-1]) else 1
        if val is not None:
            figures_dict["SUPERTREND"] = round(val, 5)
            sig = "bullish" if dir_val == 1 else "bearish"
            summary_dict["Supertrend"] = {
                "name": "Supertrend",
                "category": "overlay",
                "latest": round(val, 5),
                "prev": None,
                "delta": None,
                "slope": "rising" if sig == "bullish" else "falling",
                "signal": sig,
                "details": f"Supertrend {sig} support/resistance at {val:.5f}",
            }

    # 9. Ichimoku
    ichi_cfg = overlays.get("ichimoku", {})
    if ichi_cfg.get("enabled", False):
        ichi_dict = compute_ichimoku_series(
            high_s,
            low_s,
            close_s,
            tenkan_period=ichi_cfg.get("tenkan", 9),
            kijun_period=ichi_cfg.get("kijun", 26),
            senkou_b_period=ichi_cfg.get("senkou_b", 52),
        )
        series_dict["ichimoku_tenkan"] = _pack_series(ichi_dict["tenkan_sen"])
        series_dict["ichimoku_kijun"] = _pack_series(ichi_dict["kijun_sen"])
        series_dict["ichimoku_senkou_a"] = _pack_series(ichi_dict["senkou_span_a"])
        series_dict["ichimoku_senkou_b"] = _pack_series(ichi_dict["senkou_span_b"])

        tk_v = float(ichi_dict["tenkan_sen"].iloc[-1]) if pd.notna(ichi_dict["tenkan_sen"].iloc[-1]) else None
        kj_v = float(ichi_dict["kijun_sen"].iloc[-1]) if pd.notna(ichi_dict["kijun_sen"].iloc[-1]) else None
        sa_v = float(ichi_dict["senkou_span_a"].iloc[-1]) if pd.notna(ichi_dict["senkou_span_a"].iloc[-1]) else None
        sb_v = float(ichi_dict["senkou_span_b"].iloc[-1]) if pd.notna(ichi_dict["senkou_span_b"].iloc[-1]) else None

        if tk_v is not None:
            figures_dict["ICHIMOKU_TENKAN"] = round(tk_v, 5)
        if kj_v is not None:
            figures_dict["ICHIMOKU_KIJUN"] = round(kj_v, 5)
        if sa_v is not None:
            figures_dict["ICHIMOKU_SENKOU_A"] = round(sa_v, 5)
        if sb_v is not None:
            figures_dict["ICHIMOKU_SENKOU_B"] = round(sb_v, 5)

        sig = "neutral"
        if sa_v is not None and sb_v is not None:
            cloud_top = max(sa_v, sb_v)
            cloud_bottom = min(sa_v, sb_v)
            if last_close > cloud_top:
                sig = "bullish"
            elif last_close < cloud_bottom:
                sig = "bearish"

        summary_dict["Ichimoku"] = {
            "name": "Ichimoku",
            "category": "overlay",
            "latest": {"tenkan": tk_v, "kijun": kj_v, "senkou_a": sa_v, "senkou_b": sb_v},
            "prev": None,
            "delta": None,
            "slope": "flat",
            "signal": sig,
            "details": f"Price vs Cloud: {sig}, TK Cross: {'bullish' if (tk_v and kj_v and tk_v > kj_v) else 'bearish'}",
        }

    # 10. Pivot Points
    pp_cfg = overlays.get("pivot_points", {})
    pivot_dict: Optional[dict[str, Any]] = None
    if pp_cfg.get("enabled", False):
        method = pp_cfg.get("method", "classic")
        bar = work_df.iloc[-2] if len(work_df) >= 2 else work_df.iloc[-1]
        pivot_dict = compute_pivot_points(float(bar["high"]), float(bar["low"]), float(bar["close"]), method=method)
        if "pivot" in pivot_dict:
            figures_dict["PIVOT"] = round(float(pivot_dict["pivot"]), 5)
            for k in ("r1", "r2", "r3", "s1", "s2", "s3"):
                if k in pivot_dict:
                    figures_dict[f"PIVOT_{k.upper()}"] = round(float(pivot_dict[k]), 5)

    # 11. Oscillators: Volume
    vol_cfg = oscillators.get("volume", {})
    if vol_cfg.get("enabled", False):
        v_pts: list[dict[str, Any]] = []
        for t, idx in zip(target_ts, target_idx):
            v = vol_s.get(idx)
            c = close_s.get(idx)
            o = open_s.get(idx)
            if v is not None and pd.notna(v):
                v_pts.append(
                    {
                        "time": t,
                        "value": round(float(v), 2),
                        "bullish": bool(c >= o)
                        if (c is not None and o is not None and pd.notna(c) and pd.notna(o))
                        else True,
                    }
                )
        series_dict["volume"] = v_pts
        ma_p = vol_cfg.get("ma_period", 20)
        vol_ma = pd.Series(vol_s.rolling(ma_p).mean(), index=vol_s.index)
        series_dict["volume_ma"] = _pack_series(vol_ma)

    # 12. Oscillators: RSI
    rsi_cfg = oscillators.get("rsi", {})
    if rsi_cfg.get("enabled", False):
        p = rsi_cfg.get("period", 14)
        rsi_s = compute_rsi(close_s, period=p)
        series_dict["rsi"] = _pack_series(rsi_s)
        val = float(rsi_s.iloc[-1]) if pd.notna(rsi_s.iloc[-1]) else None
        prev_val = float(rsi_s.iloc[-2]) if len(rsi_s) >= 2 and pd.notna(rsi_s.iloc[-2]) else val
        if val is not None:
            figures_dict[f"RSI_{p}"] = round(val, 2)
            delta = round(val - prev_val, 2) if prev_val is not None else None
            slope = (
                "rising"
                if (delta is not None and delta > 0.05)
                else ("falling" if (delta is not None and delta < -0.05) else "flat")
            )
            sig = "bullish" if val > 50.0 else ("bearish" if val < 50.0 else "neutral")
            ob = float(rsi_cfg.get("overbought", 70.0))
            os_ = float(rsi_cfg.get("oversold", 30.0))
            regime = "Overbought" if val >= ob else ("Oversold" if val <= os_ else "Neutral")
            summary_dict[f"RSI_{p}"] = {
                "name": f"RSI {p}",
                "category": "oscillator",
                "latest": round(val, 2),
                "prev": round(prev_val, 2) if prev_val is not None else None,
                "delta": delta,
                "slope": slope,
                "signal": sig,
                "details": f"RSI_{p} at {val:.1f} ({regime}), slope is {slope}",
            }

    # 13. Oscillators: MACD
    macd_cfg = oscillators.get("macd", {})
    if macd_cfg.get("enabled", False):
        m_line, m_sig, m_hist = compute_macd(
            close_s,
            fast=macd_cfg.get("fast", 12),
            slow=macd_cfg.get("slow", 26),
            signal=macd_cfg.get("signal", 9),
        )
        series_dict["macd_line"] = _pack_series(m_line)
        series_dict["macd_signal"] = _pack_series(m_sig)
        series_dict["macd_hist"] = _pack_series(m_hist)
        l_val = float(m_line.iloc[-1]) if pd.notna(m_line.iloc[-1]) else None
        s_val = float(m_sig.iloc[-1]) if pd.notna(m_sig.iloc[-1]) else None
        h_val = float(m_hist.iloc[-1]) if pd.notna(m_hist.iloc[-1]) else None
        prev_h = float(m_hist.iloc[-2]) if len(m_hist) >= 2 and pd.notna(m_hist.iloc[-2]) else h_val
        if l_val is not None and s_val is not None and h_val is not None:
            figures_dict["MACD_LINE"] = round(l_val, 5)
            figures_dict["MACD_SIGNAL"] = round(s_val, 5)
            figures_dict["MACD_HIST"] = round(h_val, 5)
            delta = round(h_val - prev_h, 6) if prev_h is not None else None
            slope = (
                "rising"
                if (delta is not None and delta > 1e-7)
                else ("falling" if (delta is not None and delta < -1e-7) else "flat")
            )
            sig = "bullish" if h_val > 0 else ("bearish" if h_val < 0 else "neutral")
            summary_dict["MACD"] = {
                "name": "MACD",
                "category": "oscillator",
                "latest": {"macd": round(l_val, 5), "signal": round(s_val, 5), "histogram": round(h_val, 5)},
                "prev": round(prev_h, 5) if prev_h is not None else None,
                "delta": delta,
                "slope": slope,
                "signal": sig,
                "details": f"Histogram {h_val:.5f} ({sig}), slope {slope}",
            }

    # 14. Oscillators: Stochastic
    stoch_cfg = oscillators.get("stochastic", {})
    if stoch_cfg.get("enabled", False):
        st_k, st_d = compute_stochastic(
            high_s,
            low_s,
            close_s,
            k_period=stoch_cfg.get("k_period", 14),
            d_period=stoch_cfg.get("d_period", 3),
        )
        series_dict["stoch_k"] = _pack_series(st_k)
        series_dict["stoch_d"] = _pack_series(st_d)
        k_val = float(st_k.iloc[-1]) if pd.notna(st_k.iloc[-1]) else None
        d_val = float(st_d.iloc[-1]) if pd.notna(st_d.iloc[-1]) else None
        if k_val is not None and d_val is not None:
            figures_dict["STOCH_K"] = round(k_val, 2)
            figures_dict["STOCH_D"] = round(d_val, 2)
            sig = "bullish" if k_val > d_val else ("bearish" if k_val < d_val else "neutral")
            summary_dict["Stochastic"] = {
                "name": "Stochastic",
                "category": "oscillator",
                "latest": {"k": round(k_val, 2), "d": round(d_val, 2)},
                "prev": None,
                "delta": None,
                "slope": "flat",
                "signal": sig,
                "details": f"%K ({k_val:.1f}) vs %D ({d_val:.1f}) is {sig}",
            }

    # 15. Oscillators: ADX
    adx_cfg = oscillators.get("adx", {})
    if adx_cfg.get("enabled", False):
        p = adx_cfg.get("period", 14)
        adx_v, p_di, m_di = compute_adx(high_s, low_s, close_s, period=p)
        series_dict["adx"] = _pack_series(adx_v)
        series_dict["plus_di"] = _pack_series(p_di)
        series_dict["minus_di"] = _pack_series(m_di)
        val = float(adx_v.iloc[-1]) if pd.notna(adx_v.iloc[-1]) else None
        pos = float(p_di.iloc[-1]) if pd.notna(p_di.iloc[-1]) else None
        neg = float(m_di.iloc[-1]) if pd.notna(m_di.iloc[-1]) else None
        if val is not None and pos is not None and neg is not None:
            figures_dict[f"ADX_{p}"] = round(val, 2)
            figures_dict["PLUS_DI"] = round(pos, 2)
            figures_dict["MINUS_DI"] = round(neg, 2)
            if val >= 25.0:
                sig = "bullish" if pos > neg else "bearish"
                details = f"Strong trend (ADX {val:.1f}), +DI ({pos:.1f}) vs -DI ({neg:.1f})"
            else:
                sig = "neutral"
                details = f"Rangebound / non-trending (ADX {val:.1f})"
            summary_dict[f"ADX_{p}"] = {
                "name": f"ADX {p}",
                "category": "oscillator",
                "latest": {"adx": round(val, 2), "plus_di": round(pos, 2), "minus_di": round(neg, 2)},
                "prev": None,
                "delta": None,
                "slope": "flat",
                "signal": sig,
                "details": details,
            }

    # 16. Oscillators: ATR
    atr_cfg = oscillators.get("atr", {})
    if atr_cfg.get("enabled", False):
        p = atr_cfg.get("period", 14)
        atr_s = compute_atr(high_s, low_s, close_s, period=p)
        series_dict["atr"] = _pack_series(atr_s)
        val = float(atr_s.iloc[-1]) if pd.notna(atr_s.iloc[-1]) else None
        prev_val = float(atr_s.iloc[-2]) if len(atr_s) >= 2 and pd.notna(atr_s.iloc[-2]) else val
        if val is not None:
            figures_dict[f"ATR_{p}"] = round(val, 5)
            delta = round(val - prev_val, 6) if prev_val is not None else None
            slope = (
                "rising"
                if (delta is not None and delta > 1e-7)
                else ("falling" if (delta is not None and delta < -1e-7) else "flat")
            )
            summary_dict[f"ATR_{p}"] = {
                "name": f"ATR {p}",
                "category": "oscillator",
                "latest": round(val, 5),
                "prev": round(prev_val, 5) if prev_val is not None else None,
                "delta": delta,
                "slope": slope,
                "signal": "neutral",
                "details": f"ATR_{p} volatility {val:.5f}, slope is {slope}",
            }

    # 17. Oscillators: CVD / Volatility
    cvd_cfg = oscillators.get("cvd_volatility", {})
    if cvd_cfg.get("enabled", False):
        w = cvd_cfg.get("window", 20)
        cvd_s = compute_cvd_series(open_s, high_s, low_s, close_s, vol_s)
        yz_s = compute_yang_zhang_volatility(work_df, window=w)
        ac1_s = compute_lag1_autocorrelation(close_s, window=w)
        series_dict["cvd"] = _pack_series(cvd_s)
        series_dict["yz_vol"] = _pack_series(yz_s)
        series_dict["ac1"] = _pack_series(ac1_s)

        cvd_val = float(cvd_s.iloc[-1]) if pd.notna(cvd_s.iloc[-1]) else None
        prev_cvd = float(cvd_s.iloc[-2]) if len(cvd_s) >= 2 and pd.notna(cvd_s.iloc[-2]) else cvd_val
        yz_val = float(yz_s.iloc[-1]) if pd.notna(yz_s.iloc[-1]) else None
        ac1_val = float(ac1_s.iloc[-1]) if pd.notna(ac1_s.iloc[-1]) else None

        if cvd_val is not None:
            figures_dict["CVD"] = round(cvd_val, 2)
            delta = round(cvd_val - prev_cvd, 2) if prev_cvd is not None else None
            sig = (
                "bullish"
                if (delta is not None and delta > 0)
                else ("bearish" if (delta is not None and delta < 0) else "neutral")
            )
            summary_dict["CVD"] = {
                "name": "CVD",
                "category": "oscillator",
                "latest": round(cvd_val, 2),
                "prev": round(prev_cvd, 2) if prev_cvd is not None else None,
                "delta": delta,
                "slope": "rising" if (delta is not None and delta > 0) else "falling",
                "signal": sig,
                "details": f"CVD Net Delta: {cvd_val:.1f} (bar delta {delta})",
            }
        if yz_val is not None:
            figures_dict["YANG_ZHANG_VOL"] = round(yz_val, 6)
        if ac1_val is not None:
            figures_dict["AC1"] = round(ac1_val, 4)

    # Overall Alignment & Bias
    bullish_count = sum(1 for item in summary_dict.values() if item.get("signal") == "bullish")
    bearish_count = sum(1 for item in summary_dict.values() if item.get("signal") == "bearish")
    neutral_count = sum(1 for item in summary_dict.values() if item.get("signal") == "neutral")
    total_directional = bullish_count + bearish_count

    if total_directional > 0:
        alignment_ratio = round(max(bullish_count, bearish_count) / total_directional, 4)
    else:
        alignment_ratio = 0.0

    if bullish_count > bearish_count:
        bias = "bullish"
    elif bearish_count > bullish_count:
        bias = "bearish"
    else:
        bias = "neutral"

    if alignment_ratio >= 0.75 and total_directional >= 3:
        confluence_adj = 2
    elif alignment_ratio >= 0.60:
        confluence_adj = 1
    else:
        confluence_adj = 0

    overall = {
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "total_directional": total_directional,
        "bias": bias,
        "alignment_ratio": alignment_ratio,
        "alignment_pct": round(alignment_ratio * 100.0, 1),
        "confluence_adjustment": confluence_adj,
    }

    return {
        "workspace_config": cfg,
        "series": series_dict,
        "pivot_points": pivot_dict,
        "summary": summary_dict,
        "overall": overall,
        "declared_figures": figures_dict,
    }
