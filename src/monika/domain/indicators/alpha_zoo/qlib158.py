# ==============================================================================
# File: indicators/alpha_zoo/qlib158.py
# Monika Quantitative Alpha Zoo: Microsoft Qlib 158 Formulations for MT5
# ==============================================================================

"""
Microsoft Qlib 158 Factor Implementations for MT5 Continuous Financial Time Series.

Includes:
- Volume-Weighted Moving Volatility (WVMA) at 5, 10, 20, 60 bars.
- Raw Stochastic Value (RSV) at 5, 10, 20, 60 bars.
- Time-series Residual (RESI) & R-squared (RSQR) at 5, 10, 20 bars.
- Candlestick structural ratios: KMID, KLEN, KMID2, KUP, KLOW, KSFT.
- Volume dynamic ratios: VMA, VSTD.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from monika.domain.indicators.alpha_zoo.meta import AlphaMeta
from monika.domain.indicators.alpha_zoo.registry import FactorRegistry
from monika.domain.indicators.factor_primitives import safe_div, ts_max, ts_mean, ts_min, ts_std

# ==============================================================================
# CANDLESTICK STRUCTURE RATIOS
# ==============================================================================


@FactorRegistry.register(
    AlphaMeta(
        name="qlib_kmid",
        category="momentum",
        lookback=1,
        columns_required=["open", "close"],
        min_warmup_bars=1,
        decay_horizon=3,
        direction="positive_bullish",
        formula_latex=r"\frac{close - open}{open}",
        description="Relative candle body magnitude to open price.",
    )
)
def qlib_kmid(df: pd.DataFrame) -> pd.Series:
    c = pd.Series(df["close"])
    o = pd.Series(df["open"])
    return safe_div(c - o, o)


@FactorRegistry.register(
    AlphaMeta(
        name="qlib_klen",
        category="volatility",
        lookback=1,
        columns_required=["open", "high", "low"],
        min_warmup_bars=1,
        decay_horizon=3,
        direction="neutral_volatility",
        formula_latex=r"\frac{high - low}{open}",
        description="Relative full candle range to open price.",
    )
)
def qlib_klen(df: pd.DataFrame) -> pd.Series:
    h = pd.Series(df["high"])
    l = pd.Series(df["low"])
    o = pd.Series(df["open"])
    return safe_div(h - l, o)


@FactorRegistry.register(
    AlphaMeta(
        name="qlib_kup",
        category="mean_reversion",
        lookback=1,
        columns_required=["open", "high", "close"],
        min_warmup_bars=1,
        decay_horizon=2,
        direction="positive_bearish",
        formula_latex=r"\frac{high - \max(open, close)}{open}",
        description="Upper shadow length relative to open price (selling pressure).",
    )
)
def qlib_kup(df: pd.DataFrame) -> pd.Series:
    o = pd.Series(df["open"])
    c = pd.Series(df["close"])
    h = pd.Series(df["high"])
    top = pd.Series(np.maximum(np.asarray(o, dtype=np.float64), np.asarray(c, dtype=np.float64)), index=df.index)
    return safe_div(h - top, o)


@FactorRegistry.register(
    AlphaMeta(
        name="qlib_klow",
        category="mean_reversion",
        lookback=1,
        columns_required=["open", "low", "close"],
        min_warmup_bars=1,
        decay_horizon=2,
        direction="positive_bullish",
        formula_latex=r"\frac{\min(open, close) - low}{open}",
        description="Lower shadow length relative to open price (buying absorption).",
    )
)
def qlib_klow(df: pd.DataFrame) -> pd.Series:
    o = pd.Series(df["open"])
    c = pd.Series(df["close"])
    l = pd.Series(df["low"])
    bot = pd.Series(np.minimum(np.asarray(o, dtype=np.float64), np.asarray(c, dtype=np.float64)), index=df.index)
    return safe_div(bot - l, o)


@FactorRegistry.register(
    AlphaMeta(
        name="qlib_ksft",
        category="momentum",
        lookback=1,
        columns_required=["open", "high", "low", "close"],
        min_warmup_bars=1,
        decay_horizon=3,
        direction="positive_bullish",
        formula_latex=r"\frac{2 \cdot close - open - high - low}{high - low}",
        description="Candle directional close location within the high-low span.",
    )
)
def qlib_ksft(df: pd.DataFrame) -> pd.Series:
    c = pd.Series(df["close"])
    o = pd.Series(df["open"])
    h = pd.Series(df["high"])
    l = pd.Series(df["low"])
    num = 2.0 * c - o - h - l
    den = h - l
    return safe_div(num, den)


# ==============================================================================
# VOLUME-WEIGHTED MOVING VOLATILITY (WVMA)
# ==============================================================================


def _calc_wvma(df: pd.DataFrame, window: int) -> pd.Series:
    c = pd.Series(df["close"])
    v = pd.Series(df["volume"], dtype=float)
    ret = c.pct_change()
    abs_vol = pd.Series(ret.abs() * v, index=df.index)
    std_val = pd.Series(abs_vol.rolling(window, min_periods=window).std())
    mean_val = pd.Series(abs_vol.rolling(window, min_periods=window).mean())
    return safe_div(std_val, mean_val)


def _register_wvma(window: int) -> None:
    meta_with_us = AlphaMeta(
        name=f"qlib_wvma_{window}",
        category="volatility",
        lookback=window,
        columns_required=["close", "volume"],
        min_warmup_bars=window + 1,
        decay_horizon=window // 2 + 1,
        direction="neutral_volatility",
        formula_latex=rf"\frac{{\text{{ts\_std}}(|\Delta C/C_{{-1}}| \cdot V, {window})}}{{\text{{ts\_mean}}(|\Delta C/C_{{-1}}| \cdot V, {window})}}",
        description=f"Volume-Weighted Moving Volatility over {window} bars.",
    )
    meta_without_us = AlphaMeta(
        name=f"qlib_wvma{window}",
        category="volatility",
        lookback=window,
        columns_required=["close", "volume"],
        min_warmup_bars=window + 1,
        decay_horizon=window // 2 + 1,
        direction="neutral_volatility",
        formula_latex=rf"\frac{{\text{{ts\_std}}(|\Delta C/C_{{-1}}| \cdot V, {window})}}{{\text{{ts\_mean}}(|\Delta C/C_{{-1}}| \cdot V, {window})}}",
        description=f"Volume-Weighted Moving Volatility over {window} bars.",
    )

    def _fn(df: pd.DataFrame) -> pd.Series:
        return _calc_wvma(df, window)

    FactorRegistry.register(meta_with_us)(_fn)


for w in (5, 10, 20, 60):
    _register_wvma(w)


# ==============================================================================
# RAW STOCHASTIC VALUE (RSV)
# ==============================================================================


def _calc_rsv(df: pd.DataFrame, window: int) -> pd.Series:
    lowest = df["low"].rolling(window, min_periods=window).min()
    highest = df["high"].rolling(window, min_periods=window).max()
    num = df["close"] - lowest
    den = highest - lowest
    return safe_div(num, den)


def _register_rsv(window: int) -> None:
    meta_with_us = AlphaMeta(
        name=f"qlib_rsv_{window}",
        category="mean_reversion",
        lookback=window,
        columns_required=["high", "low", "close"],
        min_warmup_bars=window,
        decay_horizon=window // 3 + 1,
        direction="positive_bullish",
        formula_latex=rf"\frac{{C - \min_{{{window}}}(L)}}{{\max_{{{window}}}(H) - \min_{{{window}}}(L)}}",
        description=f"Raw Stochastic Oscillator position over {window} bars.",
    )
    meta_without_us = AlphaMeta(
        name=f"qlib_rsv{window}",
        category="mean_reversion",
        lookback=window,
        columns_required=["high", "low", "close"],
        min_warmup_bars=window,
        decay_horizon=window // 3 + 1,
        direction="positive_bullish",
        formula_latex=rf"\frac{{C - \min_{{{window}}}(L)}}{{\max_{{{window}}}(H) - \min_{{{window}}}(L)}}",
        description=f"Raw Stochastic Oscillator position over {window} bars.",
    )

    def _fn(df: pd.DataFrame) -> pd.Series:
        return _calc_rsv(df, window)

    FactorRegistry.register(meta_with_us)(_fn)


for w in (5, 10, 20, 60):
    _register_rsv(w)


# ==============================================================================
# RESIDUAL & R-SQUARED OF PRICE ON TIME (RESI & RSQR)
# ==============================================================================


def _calc_resi_rsqr(df: pd.DataFrame, window: int) -> tuple[pd.Series, pd.Series]:
    """Calculates linear regression of close on time t=0..window-1 using vectorized rolling windows."""
    y = df["close"].to_numpy(dtype=np.float64, copy=False)
    n = len(y)
    resi = np.full(n, np.nan, dtype=np.float64)
    rsqr = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return (
            pd.Series(resi, index=df.index),
            pd.Series(rsqr, index=df.index),
        )

    # Precalculate x statistics (constant across all windows)
    x = np.arange(window, dtype=np.float64)
    x_mean = (window - 1.0) / 2.0
    x_dm = x - x_mean
    sum_x_dm2 = float(np.sum(x_dm**2))

    # Strided sliding window: shape (n - window + 1, window)
    windows = np.lib.stride_tricks.sliding_window_view(y, window_shape=window)

    # Mask windows containing any NaN
    valid_mask = ~np.isnan(windows).any(axis=1)

    if not np.any(valid_mask):
        return (
            pd.Series(resi, index=df.index),
            pd.Series(rsqr, index=df.index),
        )

    valid_windows = windows[valid_mask]
    y_mean = np.mean(valid_windows, axis=1)
    y_dm = valid_windows - y_mean[:, None]
    cov_xy = np.dot(y_dm, x_dm)

    slope = cov_xy / sum_x_dm2 if sum_x_dm2 > 1e-12 else np.zeros_like(cov_xy)
    intercept = y_mean - slope * x_mean

    # Predicted value at the end of the window (t = window - 1)
    y_pred = intercept + slope * (window - 1)
    residuals = valid_windows[:, -1] - y_pred

    ss_tot = np.sum(y_dm**2, axis=1)
    # R^2 = (cov_xy^2) / (sum_x_dm2 * ss_tot)
    if sum_x_dm2 > 1e-12:
        denom = sum_x_dm2 * ss_tot
        safe_denom = np.where(denom > 1e-12, denom, 1.0)
        r2 = np.where(denom > 1e-12, (cov_xy**2) / safe_denom, 0.0)
    else:
        r2 = np.zeros_like(ss_tot)

    rsqr_vals = np.clip(r2, 0.0, 1.0)

    # Fill back into output arrays
    dest_indices = np.arange(window - 1, n)[valid_mask]
    resi[dest_indices] = residuals
    rsqr[dest_indices] = rsqr_vals

    return (
        pd.Series(resi, index=df.index),
        pd.Series(rsqr, index=df.index),
    )


def _register_resi_rsqr(window: int) -> None:
    meta_resi = AlphaMeta(
        name=f"qlib_resi_{window}",
        category="mean_reversion",
        lookback=window,
        columns_required=["close"],
        min_warmup_bars=window,
        decay_horizon=3,
        direction="positive_bullish",
        formula_latex=rf"C - (\hat{{\alpha}} + \hat{{\beta}} \cdot {window})",
        description=f"Linear trend residual over {window} bars.",
    )
    meta_resi_no_us = AlphaMeta(
        name=f"qlib_resi{window}",
        category="mean_reversion",
        lookback=window,
        columns_required=["close"],
        min_warmup_bars=window,
        decay_horizon=3,
        direction="positive_bullish",
        formula_latex=rf"C - (\hat{{\alpha}} + \hat{{\beta}} \cdot {window})",
        description=f"Linear trend residual over {window} bars.",
    )

    def _fn_resi(df: pd.DataFrame) -> pd.Series:
        resi, _ = _calc_resi_rsqr(df, window)
        return resi

    FactorRegistry.register(meta_resi)(_fn_resi)

    meta_rsqr = AlphaMeta(
        name=f"qlib_rsqr_{window}",
        category="trend",
        lookback=window,
        columns_required=["close"],
        min_warmup_bars=window,
        decay_horizon=5,
        direction="positive_bullish",
        formula_latex=rf"R^2(C, t)_{{{window}}}",
        description=f"Goodness of fit (R-squared) to linear trend over {window} bars.",
    )
    meta_rsqr_no_us = AlphaMeta(
        name=f"qlib_rsqr{window}",
        category="trend",
        lookback=window,
        columns_required=["close"],
        min_warmup_bars=window,
        decay_horizon=5,
        direction="positive_bullish",
        formula_latex=rf"R^2(C, t)_{{{window}}}",
        description=f"Goodness of fit (R-squared) to linear trend over {window} bars.",
    )

    def _fn_rsqr(df: pd.DataFrame) -> pd.Series:
        _, rsqr = _calc_resi_rsqr(df, window)
        return rsqr

    FactorRegistry.register(meta_rsqr)(_fn_rsqr)


for w in (5, 10, 20):
    _register_resi_rsqr(w)


# ==============================================================================
# VOLUME DYNAMICS (VMA & VSTD)
# ==============================================================================

for w in (5, 10, 20):

    @FactorRegistry.register(
        AlphaMeta(
            name=f"qlib_vma{w}",
            category="volume",
            lookback=w,
            columns_required=["volume"],
            min_warmup_bars=w,
            decay_horizon=3,
            direction="neutral_volatility",
            formula_latex=rf"\frac{{\text{{ts\_mean}}(V, {w})}}{{V_{{t}}}}",
            description=f"Moving average volume ratio over {w} bars.",
        )
    )
    def _vma_factory(df: pd.DataFrame, _w=w) -> pd.Series:
        vol = df["volume"].astype(float)
        mean_v = vol.rolling(_w, min_periods=_w).mean()
        return safe_div(mean_v, vol)

    @FactorRegistry.register(
        AlphaMeta(
            name=f"qlib_vstd{w}",
            category="volume",
            lookback=w,
            columns_required=["volume"],
            min_warmup_bars=w,
            decay_horizon=3,
            direction="neutral_volatility",
            formula_latex=rf"\frac{{\text{{ts\_std}}(V, {w})}}{{\text{{ts\_mean}}(V, {w})}}",
            description=f"Volume coefficient of variation over {w} bars.",
        )
    )
    def _vstd_factory(df: pd.DataFrame, _w=w) -> pd.Series:
        vol = df["volume"].astype(float)
        std_v = vol.rolling(_w, min_periods=_w).std()
        mean_v = vol.rolling(_w, min_periods=_w).mean()
        return safe_div(std_v, mean_v)
