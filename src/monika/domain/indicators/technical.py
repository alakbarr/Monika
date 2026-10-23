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
    rs = (log_ho * log_hc + log_lo * log_lc).rolling(n).mean()

    # Overnight & open-to-close variances
    overnight_var = log_co_prev.rolling(n).var()
    oc_var = log_oc.rolling(n).var()

    k = 0.34 / (1.34 + ((n + 1) / (n - 1)))
    yz_var = overnight_var + (oc_var * k) + (rs * (1.0 - k))

    return yz_var.apply(lambda x: float(np.sqrt(max(0.0, x))) if pd.notna(x) else 0.0)


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

    tenkan = (high.rolling(tenkan_period).max() + low.rolling(tenkan_period).min()) / 2.0
    kijun = (high.rolling(kijun_period).max() + low.rolling(kijun_period).min()) / 2.0
    senkou_a = ((tenkan + kijun) / 2.0).shift(kijun_period)
    senkou_b = ((high.rolling(senkou_b_period).max() + low.rolling(senkou_b_period).min()) / 2.0).shift(kijun_period)
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
