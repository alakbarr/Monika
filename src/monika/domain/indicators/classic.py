# ==============================================================================
# File: domain/indicators/classic.py
# ==============================================================================

"""
Pure Mathematical and Statistical Indicator Functions.
Includes moving averages, oscillators, volatility, and divergence detectors.
Modernized with Polars vectorization and native Rust C-ABI acceleration (monika_core_rs).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd
import polars as pl

from monika.core.native.rust_bridge import (
    atr_f64,
    bollinger_bands_f64,
    ema_f64,
    macd_f64,
    rsi_f64,
    sma_f64,
    stochastic_f64,
    yang_zhang_f64,
)
from monika.domain.indicators.polars_indicators import (
    compute_adx_polars,
    compute_atr_polars,
    compute_bollinger_bands_polars,
    compute_ema_polars,
    compute_macd_polars,
    compute_rsi_polars,
    compute_sma_polars,
    compute_stochastic_polars,
    compute_yang_zhang_polars,
)

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
    close_p = df["close"].astype(float)

    # Fast-path via native Rust C-ABI kernel (monika_core_rs)
    yz_arr = yang_zhang_f64(
        open_p.to_numpy(dtype=np.float64),
        high_p.to_numpy(dtype=np.float64),
        low_p.to_numpy(dtype=np.float64),
        close_p.to_numpy(dtype=np.float64),
        n,
    )
    if yz_arr is not None:
        # Fill warmup with 0.0 to match legacy interface contract
        return pd.Series(np.nan_to_num(yz_arr, nan=0.0), index=df.index, dtype=float)

    # Vectorized Polars fallback
    try:
        pl_df = pl.DataFrame(
            {
                "open": open_p.to_numpy(dtype=np.float64),
                "high": high_p.to_numpy(dtype=np.float64),
                "low": low_p.to_numpy(dtype=np.float64),
                "close": close_p.to_numpy(dtype=np.float64),
            }
        )
        yz_pl = compute_yang_zhang_polars(pl_df, window=n)
        return pd.Series(np.nan_to_num(yz_pl.to_numpy(), nan=0.0), index=df.index, dtype=float)
    except Exception:
        pass

    # Log components pure numpy fallback
    log_oc = pd.Series(np.log(close_p / (open_p + 1e-12)), index=df.index)
    log_co_prev = pd.Series(np.log(open_p / (close_p.shift(1) + 1e-12)), index=df.index)
    log_ho = pd.Series(np.log(high_p / (open_p + 1e-12)), index=df.index)
    log_lo = pd.Series(np.log(low_p / (open_p + 1e-12)), index=df.index)
    log_hc = pd.Series(np.log(high_p / (close_p + 1e-12)), index=df.index)
    log_lc = pd.Series(np.log(low_p / (close_p + 1e-12)), index=df.index)

    rs = pd.Series((log_ho * log_hc + log_lo * log_lc).rolling(n).mean(), index=df.index)
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
    """Computes SMAs and EMAs for specified periods with native Rust acceleration and Polars fallback."""
    result: dict[str, pd.Series] = {}
    close_vals = close.to_numpy(dtype=float) if isinstance(close, pd.Series) else np.asarray(close, dtype=float)
    idx = close.index if isinstance(close, pd.Series) else None
    pl_series = pl.Series("close", close_vals)

    for p in sma_periods:
        s_arr = sma_f64(close_vals, p)
        if s_arr is not None:
            result[f"SMA_{p}"] = pd.Series(s_arr, index=idx)
        else:
            s_pl = compute_sma_polars(pl_series, period=p)
            result[f"SMA_{p}"] = pd.Series(s_pl.to_numpy(), index=idx)

    for p in ema_periods:
        e_arr = ema_f64(close_vals, p)
        if e_arr is not None:
            result[f"EMA_{p}"] = pd.Series(e_arr, index=idx)
        else:
            e_pl = compute_ema_polars(pl_series, period=p)
            result[f"EMA_{p}"] = pd.Series(e_pl.to_numpy(), index=idx)

    return result


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Computes RSI (Relative Strength Index) with native Rust acceleration and Polars fallback."""
    close_vals = close.to_numpy(dtype=float) if isinstance(close, pd.Series) else np.asarray(close, dtype=float)
    idx = close.index if isinstance(close, pd.Series) else None

    r_arr = rsi_f64(close_vals, period)
    if r_arr is not None:
        return pd.Series(r_arr, index=idx)

    r_pl = compute_rsi_polars(pl.Series("close", close_vals), period=period)
    return pd.Series(r_pl.to_numpy(), index=idx)


def compute_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Computes Stochastic %K and %D with native Rust acceleration and Polars fallback."""
    high_vals = high.to_numpy(dtype=float) if isinstance(high, pd.Series) else np.asarray(high, dtype=float)
    low_vals = low.to_numpy(dtype=float) if isinstance(low, pd.Series) else np.asarray(low, dtype=float)
    close_vals = close.to_numpy(dtype=float) if isinstance(close, pd.Series) else np.asarray(close, dtype=float)
    idx = close.index if isinstance(close, pd.Series) else None

    stoch_res = stochastic_f64(high_vals, low_vals, close_vals, k_period, d_period)
    if stoch_res is not None:
        out_k, out_d = stoch_res
        return pd.Series(out_k, index=idx), pd.Series(out_d, index=idx)

    pl_df = pl.DataFrame(
        {
            "high": high_vals,
            "low": low_vals,
            "close": close_vals,
        }
    )
    stoch_df = compute_stochastic_polars(pl_df, k_period=k_period, d_period=d_period)
    return pd.Series(stoch_df["stoch_k"].to_numpy(), index=idx), pd.Series(stoch_df["stoch_d"].to_numpy(), index=idx)


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Computes MACD line, signal line, and histogram with native Rust acceleration and Polars fallback."""
    close_vals = close.to_numpy(dtype=float) if isinstance(close, pd.Series) else np.asarray(close, dtype=float)
    idx = close.index if isinstance(close, pd.Series) else None

    macd_res = macd_f64(close_vals, fast, slow, signal)
    if macd_res is not None:
        m_line, s_line, h_diff = macd_res
        return pd.Series(m_line, index=idx), pd.Series(s_line, index=idx), pd.Series(h_diff, index=idx)

    m_df = compute_macd_polars(pl.Series("close", close_vals), fast=fast, slow=slow, signal=signal)
    return (
        pd.Series(m_df["macd"].to_numpy(), index=idx),
        pd.Series(m_df["macd_signal"].to_numpy(), index=idx),
        pd.Series(m_df["macd_diff"].to_numpy(), index=idx),
    )


def compute_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Computes Bollinger Bands: upper, middle, lower, pct_b, bandwidth with native Rust acceleration and Polars fallback."""
    close_vals = close.to_numpy(dtype=float) if isinstance(close, pd.Series) else np.asarray(close, dtype=float)
    idx = close.index if isinstance(close, pd.Series) else None

    bb_arrs = bollinger_bands_f64(close_vals, period, std_dev)
    if bb_arrs is not None:
        mavg, upper, lower = bb_arrs
        diff = upper - lower
        safe_diff = np.where(diff != 0.0, diff, 1.0)
        pct_b = np.where(diff != 0.0, (close_vals - lower) / safe_diff, 0.0)
        safe_mavg = np.where(mavg != 0.0, mavg, 1.0)
        wband = np.where(mavg != 0.0, (diff / safe_mavg) * 100.0, 0.0)
        return (
            pd.Series(upper, index=idx),
            pd.Series(mavg, index=idx),
            pd.Series(lower, index=idx),
            pd.Series(pct_b, index=idx),
            pd.Series(wband, index=idx),
        )

    bb_df = compute_bollinger_bands_polars(pl.Series("close", close_vals), period=period, num_std=std_dev)
    return (
        pd.Series(bb_df["upper"].to_numpy(), index=idx),
        pd.Series(bb_df["middle"].to_numpy(), index=idx),
        pd.Series(bb_df["lower"].to_numpy(), index=idx),
        pd.Series(bb_df["pct_b"].to_numpy(), index=idx),
        pd.Series(bb_df["bandwidth"].to_numpy(), index=idx),
    )


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Computes Average True Range with native Rust acceleration and Polars fallback."""
    h_arr = high.to_numpy(dtype=float) if isinstance(high, pd.Series) else np.asarray(high, dtype=float)
    l_arr = low.to_numpy(dtype=float) if isinstance(low, pd.Series) else np.asarray(low, dtype=float)
    c_arr = close.to_numpy(dtype=float) if isinstance(close, pd.Series) else np.asarray(close, dtype=float)
    idx = close.index if isinstance(close, pd.Series) else None

    a_arr = atr_f64(h_arr, l_arr, c_arr, period)
    if a_arr is not None:
        return pd.Series(a_arr, index=idx)

    pl_df = pl.DataFrame(
        {
            "high": h_arr,
            "low": l_arr,
            "close": c_arr,
        }
    )
    atr_pl = compute_atr_polars(pl_df, period=period)
    return pd.Series(atr_pl.to_numpy(), index=idx)


def compute_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Computes ADX, +DI, and -DI using vectorized Polars engine."""
    h_arr = high.to_numpy(dtype=float) if isinstance(high, pd.Series) else np.asarray(high, dtype=float)
    l_arr = low.to_numpy(dtype=float) if isinstance(low, pd.Series) else np.asarray(low, dtype=float)
    c_arr = close.to_numpy(dtype=float) if isinstance(close, pd.Series) else np.asarray(close, dtype=float)
    idx = close.index if isinstance(close, pd.Series) else None

    pl_df = pl.DataFrame(
        {
            "high": h_arr,
            "low": l_arr,
            "close": c_arr,
        }
    )
    adx_pl, pdi_pl, ndi_pl = compute_adx_polars(pl_df, period=period)
    return (
        pd.Series(adx_pl.to_numpy(), index=idx),
        pd.Series(pdi_pl.to_numpy(), index=idx),
        pd.Series(ndi_pl.to_numpy(), index=idx),
    )


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
            rsi = compute_rsi(close=close, period=14)
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
            m_line, _, m_diff = compute_macd(close=close)
            macd_line = m_line
            if macd_hist is None:
                macd_hist = m_diff
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
