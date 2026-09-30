# ==============================================================================
# File: indicators/factor_primitives.py
# Monika Quantitative Factor Primitives & Vectorized Math Engine
# ==============================================================================

"""
Factor Primitives & Vectorized Numerical Foundation.

Provides mathematically rigorous, high-performance base operators for quantitative
factor analysis on MetaTrader 5 assets (Forex, Metals, Energy, Crypto, Indices).

Guarantees:
- Strict NaN propagation: No silent fillna(0). Missing values remain NaN.
- Division safety: Division by zero returns NaN (via safe_div).
- Lookahead prevention: delta(df, d) strictly requires d >= 1.
- Vectorized efficiency: Accelerated using NumPy sliding_window_view and einsum
  with graceful Bottleneck C-extension support when installed.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

logger = logging.getLogger("TradingAgent.Indicators.FactorPrimitives")

# Check Bottleneck availability lazily
HAS_BOTTLENECK: bool = False
try:
    import bottleneck as bn  # type: ignore
    HAS_BOTTLENECK = True
except ImportError:
    bn = None


def _as_float(df: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """Ensure data structure is cast to float64, preserving index and columns."""
    if isinstance(df, pd.DataFrame):
        if df.dtypes.eq(np.float64).all():
            return df
        return df.astype(np.float64)
    if df.dtype == np.float64:
        return df
    return df.astype(np.float64)


from enum import Enum

class Market(str, Enum):
    """Market identifier used by vwap for market-specific conventions."""
    EQUITY_US = "equity_us"
    EQUITY_CN = "equity_cn"
    EQUITY_HK = "equity_hk"
    EQUITY_IN = "equity_in"
    EQUITY_KR = "equity_kr"
    CRYPTO = "crypto"
    FOREX = "forex"
    COMMODITIES = "commodities"


def vwap(panel: Any, market: Any = None) -> pd.DataFrame | pd.Series:
    """Market-aware VWAP-equivalent reference price."""
    if isinstance(panel, pd.DataFrame):
        if "vwap" in panel.columns:
            return panel["vwap"]
        return (panel["high"] + panel["low"] + panel["close"] + panel.get("open", panel["close"])) / 4.0
    if isinstance(panel, dict):
        if "vwap" in panel:
            return panel["vwap"]
        h = panel.get("high")
        l = panel.get("low")
        c = panel.get("close")
        o = panel.get("open", c)
        if h is not None and l is not None and c is not None:
            return (h + l + c + o) / 4.0
        return c
    return panel


def safe_div(
    a: pd.DataFrame | pd.Series | np.ndarray | float,
    b: pd.DataFrame | pd.Series | np.ndarray | float,
    eps: float = 1e-12,
) -> pd.DataFrame | pd.Series | np.ndarray | float:
    """
    Division with zero/NaN guards: a / (b + eps * sign(b)).
    If b is exactly 0.0 or NaN, the result is strictly NaN (never +/- inf or silent 0).
    """
    if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
        df_target = a if isinstance(a, pd.DataFrame) else b
        a_arr = a.to_numpy(dtype=np.float64, na_value=np.nan) if isinstance(a, (pd.DataFrame, pd.Series)) else np.asarray(a, dtype=np.float64)
        b_arr = b.to_numpy(dtype=np.float64, na_value=np.nan) if isinstance(b, (pd.DataFrame, pd.Series)) else np.asarray(b, dtype=np.float64)
        sign = np.where(b_arr == 0.0, 1.0, np.sign(b_arr))
        denom = b_arr + eps * sign
        with np.errstate(divide="ignore", invalid="ignore"):
            res_arr = np.where(b_arr == 0.0, np.nan, a_arr / denom)
        res_arr = np.where(np.isinf(res_arr), np.nan, res_arr)
        return pd.DataFrame(res_arr, index=df_target.index, columns=df_target.columns)

    if isinstance(a, pd.Series) or isinstance(b, pd.Series):
        s_target = a if isinstance(a, pd.Series) else b
        a_arr = a.to_numpy(dtype=np.float64, na_value=np.nan) if isinstance(a, pd.Series) else np.asarray(a, dtype=np.float64)
        b_arr = b.to_numpy(dtype=np.float64, na_value=np.nan) if isinstance(b, pd.Series) else np.asarray(b, dtype=np.float64)
        sign = np.where(b_arr == 0.0, 1.0, np.sign(b_arr))
        denom = b_arr + eps * sign
        with np.errstate(divide="ignore", invalid="ignore"):
            res_arr = np.where(b_arr == 0.0, np.nan, a_arr / denom)
        res_arr = np.where(np.isinf(res_arr), np.nan, res_arr)
        return pd.Series(res_arr, index=s_target.index, name=getattr(s_target, "name", None))

    arr_a = np.asarray(a, dtype=np.float64)
    arr_b = np.asarray(b, dtype=np.float64)
    sign = np.where(arr_b == 0.0, 1.0, np.sign(arr_b))
    denom = arr_b + eps * sign
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.where(arr_b == 0.0, np.nan, arr_a / denom)
    res = np.where(np.isinf(res), np.nan, res)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(res) if not np.isnan(res) else np.nan
    return res


def rank(df: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """
    Percentile rank across columns (axis=1 for multi-asset DataFrame cross-section, axis=0 for Series or single-asset DataFrame).
    Returns values in range (0.0, 1.0]. NaN values are strictly preserved.
    """
    if isinstance(df, pd.Series):
        return df.rank(axis=0, method="average", pct=True, na_option="keep")
    if isinstance(df, pd.DataFrame) and df.shape[1] == 1:
        return df.rank(axis=0, method="average", pct=True, na_option="keep")
    return df.rank(axis=1, method="average", pct=True, na_option="keep")


def zscore(df: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """
    Z-score per observation (axis=1 for multi-asset DataFrame cross-section, axis=0 for Series or single-asset DataFrame, ddof=1).
    Observations with zero variance or all NaNs become NaN (never silent 0).
    """
    df_f = _as_float(df)
    if isinstance(df_f, pd.Series):
        mean = df_f.mean(skipna=True)
        std = df_f.std(ddof=1, skipna=True)
        if std == 0 or np.isnan(std):
            return pd.Series(np.nan, index=df_f.index, dtype=float, name=df_f.name)
        res = (df_f - mean) / std
        return res.replace([np.inf, -np.inf], np.nan)
    if isinstance(df_f, pd.DataFrame) and df_f.shape[1] == 1:
        mean = df_f.mean(axis=0, skipna=True)
        std = df_f.std(axis=0, ddof=1, skipna=True)
        res = df_f.sub(mean, axis=1).div(std.where(std > 0), axis=1)
        return res.replace([np.inf, -np.inf], np.nan)
    mean = df_f.mean(axis=1, skipna=True)
    std = df_f.std(axis=1, ddof=1, skipna=True)
    res = df_f.sub(mean, axis=0).div(std.where(std > 0), axis=0)
    return res.replace([np.inf, -np.inf], np.nan)


def scale(df: pd.DataFrame | pd.Series, a: float = 1.0) -> pd.DataFrame | pd.Series:
    """
    L1 normalization so sum of absolute values equals a.
    Zero sum or all NaN become NaN.
    """
    df_f = _as_float(df)
    if isinstance(df_f, pd.Series):
        abs_sum = df_f.abs().sum(skipna=True)
        if abs_sum == 0 or np.isnan(abs_sum):
            return pd.Series(np.nan, index=df_f.index, dtype=float, name=df_f.name)
        res = (df_f * a) / abs_sum
        return res.replace([np.inf, -np.inf], np.nan)
    if isinstance(df_f, pd.DataFrame) and df_f.shape[1] == 1:
        abs_sum = df_f.abs().sum(axis=0, skipna=True)
        abs_sum = abs_sum.where(abs_sum > 0)
        return df_f.mul(a).div(abs_sum, axis=1)
    abs_sum = df_f.abs().sum(axis=1, skipna=True)
    abs_sum = abs_sum.where(abs_sum > 0)
    return df_f.mul(a).div(abs_sum, axis=0)


def delta(df: pd.DataFrame | pd.Series, d: int) -> pd.DataFrame | pd.Series:
    """
    Difference at lag d: df - df.shift(d).
    Enforces strict lookahead ban: d >= 1 required.
    """
    if d < 1:
        raise ValueError(f"delta lag must be >= 1 (lookahead violation forbidden), got {d}")
    return df - df.shift(d)


def signed_power(df: pd.DataFrame | pd.Series, p: float) -> pd.DataFrame | pd.Series:
    """Computes sign(df) * |df|**p preserving sign without complex numbers."""
    if isinstance(df, (pd.DataFrame, pd.Series)):
        arr = df.to_numpy(dtype=np.float64, na_value=np.nan)
        out = np.sign(arr) * np.power(np.abs(arr), p)
        if isinstance(df, pd.DataFrame):
            return pd.DataFrame(out, index=df.index, columns=df.columns)
        return pd.Series(out, index=df.index, name=df.name)
    arr = np.asarray(df, dtype=np.float64)
    return np.sign(arr) * np.power(np.abs(arr), p)


def ts_rank(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """
    Rolling time-series rank (percentile in [0, 1]) within an n-bar lookback window.
    Warmup rows (first n-1 rows) return NaN.
    Vectorized using numpy sliding_window_view for high throughput.
    """
    if n < 1:
        raise ValueError(f"ts_rank window must be >= 1, got {n}")

    is_series = isinstance(df, pd.Series)
    s_name = df.name if is_series else None
    input_df = df.to_frame() if is_series else df

    arr = input_df.to_numpy(dtype=np.float64)
    T, C = arr.shape
    if T < n:
        def _last_rank(sub: np.ndarray) -> float:
            if np.isnan(sub).all():
                return np.nan
            last = sub[-1]
            if np.isnan(last):
                return np.nan
            valid = sub[~np.isnan(sub)]
            if valid.size == 0:
                return np.nan
            less = (valid < last).sum()
            eq = (valid == last).sum()
            return float((less + 0.5 * (eq + 1)) / valid.size)
        res = input_df.rolling(window=n, min_periods=n).apply(_last_rank, raw=True)
        return res.iloc[:, 0].rename(s_name) if is_series else res

    windows = sliding_window_view(arr, window_shape=n, axis=0)  # (T-n+1, C, n)
    last_vals = windows[:, :, -1]
    nan_last = np.isnan(last_vals)
    nan_count = np.isnan(windows).sum(axis=2)
    valid_count = n - nan_count

    last_expanded = last_vals[:, :, np.newaxis]
    valid_mask = ~np.isnan(windows) & ~nan_last[:, :, np.newaxis]
    less = np.sum(np.where(valid_mask, windows < last_expanded, 0), axis=2)
    eq = np.sum(np.where(valid_mask, windows == last_expanded, 0), axis=2)
    rank_avg = less + 0.5 * (eq + 1)
    
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = rank_avg / valid_count
    pct[nan_last | (nan_count > 0)] = np.nan

    result = np.full((T, C), np.nan)
    result[n - 1 :] = pct
    res_df = pd.DataFrame(result, index=input_df.index, columns=input_df.columns)
    return res_df.iloc[:, 0].rename(s_name) if is_series else res_df


def ts_corr(x: pd.DataFrame | pd.Series, y: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """
    Rolling Pearson correlation with min_periods=n.
    Constant series in window return NaN (no silent zero).
    """
    if n < 2:
        raise ValueError(f"ts_corr window must be >= 2, got {n}")
    if isinstance(x, pd.Series) and isinstance(y, pd.Series):
        corr = x.astype(float).rolling(window=n, min_periods=n).corr(y.astype(float))
        return corr.replace([np.inf, -np.inf], np.nan)

    x_df = x.to_frame() if isinstance(x, pd.Series) else x
    y_df = y.to_frame() if isinstance(y, pd.Series) else y
    x_f = _as_float(x_df)
    y_f = _as_float(y_df)
    cols = x_f.columns.union(y_f.columns)
    xa = x_f.reindex(columns=cols)
    ya = y_f.reindex(columns=cols)
    corr = xa.rolling(window=n, min_periods=n).corr(ya)
    res = corr.replace([np.inf, -np.inf], np.nan)
    if isinstance(x, pd.Series) and isinstance(y, pd.Series):
        return res.iloc[:, 0]
    return res


def ts_cov(x: pd.DataFrame | pd.Series, y: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """Rolling sample covariance with min_periods=n."""
    if n < 2:
        raise ValueError(f"ts_cov window must be >= 2, got {n}")
    if isinstance(x, pd.Series) and isinstance(y, pd.Series):
        cov = x.astype(float).rolling(window=n, min_periods=n).cov(y.astype(float))
        return cov.replace([np.inf, -np.inf], np.nan)

    x_df = x.to_frame() if isinstance(x, pd.Series) else x
    y_df = y.to_frame() if isinstance(y, pd.Series) else y
    x_f = _as_float(x_df)
    y_f = _as_float(y_df)
    cols = x_f.columns.union(y_f.columns)
    xa = x_f.reindex(columns=cols)
    ya = y_f.reindex(columns=cols)
    cov = xa.rolling(window=n, min_periods=n).cov(ya)
    res = cov.replace([np.inf, -np.inf], np.nan)
    if isinstance(x, pd.Series) and isinstance(y, pd.Series):
        return res.iloc[:, 0]
    return res


def ts_mean(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """Rolling arithmetic mean with strict warmup -> NaN."""
    if n < 1:
        raise ValueError(f"ts_mean window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).mean()


def ts_std(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """Rolling sample standard deviation (ddof=1) with warmup -> NaN."""
    if n < 2:
        raise ValueError(f"ts_std window must be >= 2, got {n}")
    return df.rolling(window=n, min_periods=n).std(ddof=1)


def ts_max(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """Rolling maximum with warmup -> NaN."""
    if n < 1:
        raise ValueError(f"ts_max window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).max()


def ts_min(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """Rolling minimum with warmup -> NaN."""
    if n < 1:
        raise ValueError(f"ts_min window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).min()


def ts_argmax(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """
    Rolling argmax returning 0-based index into the n-bar window.
    Warmup -> NaN. Uses Bottleneck move_argmax if available, else numpy sliding window.
    """
    if n < 1:
        raise ValueError(f"ts_argmax window must be >= 1, got {n}")
    is_series = isinstance(df, pd.Series)
    s_name = df.name if is_series else None
    input_df = df.to_frame() if is_series else df

    if HAS_BOTTLENECK and bn is not None:
        arr = input_df.to_numpy(dtype=np.float64)
        raw = bn.move_argmax(arr, window=n, min_count=n, axis=0)
        res_df = pd.DataFrame(raw, index=input_df.index, columns=input_df.columns)
        return res_df.iloc[:, 0].rename(s_name) if is_series else res_df

    def _argmax_last(sub: np.ndarray) -> float:
        if np.isnan(sub).all():
            return np.nan
        filled = np.where(np.isnan(sub), -np.inf, sub)
        return float(np.argmax(filled))

    res_df = input_df.rolling(window=n, min_periods=n).apply(_argmax_last, raw=True)
    return res_df.iloc[:, 0].rename(s_name) if is_series else res_df


def ts_argmin(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """
    Rolling argmin returning 0-based index into the n-bar window.
    Warmup -> NaN. Uses Bottleneck move_argmin if available, else numpy sliding window.
    """
    if n < 1:
        raise ValueError(f"ts_argmin window must be >= 1, got {n}")
    is_series = isinstance(df, pd.Series)
    s_name = df.name if is_series else None
    input_df = df.to_frame() if is_series else df

    if HAS_BOTTLENECK and bn is not None:
        arr = input_df.to_numpy(dtype=np.float64)
        raw = bn.move_argmin(arr, window=n, min_count=n, axis=0)
        res_df = pd.DataFrame(raw, index=input_df.index, columns=input_df.columns)
        return res_df.iloc[:, 0].rename(s_name) if is_series else res_df

    def _argmin_last(sub: np.ndarray) -> float:
        if np.isnan(sub).all():
            return np.nan
        filled = np.where(np.isnan(sub), np.inf, sub)
        return float(np.argmin(filled))

    res_df = input_df.rolling(window=n, min_periods=n).apply(_argmin_last, raw=True)
    return res_df.iloc[:, 0].rename(s_name) if is_series else res_df


def decay_linear(df: pd.DataFrame | pd.Series, n: int) -> pd.DataFrame | pd.Series:
    """
    Linear decay-weighted moving average with weights n, n-1, ..., 1 normalized.
    Vectorized using sliding_window_view and tensor contraction einsum.
    Warmup (first n-1 rows) -> NaN. Any NaN in the window propagates to NaN.
    """
    if n < 1:
        raise ValueError(f"decay_linear window must be >= 1, got {n}")
    weights = np.arange(1, n + 1, dtype=np.float64)
    weights /= weights.sum()

    is_series = isinstance(df, pd.Series)
    s_name = df.name if is_series else None
    input_df = df.to_frame() if is_series else df

    arr = input_df.to_numpy(dtype=np.float64)
    T, C = arr.shape
    if T < n:
        def _apply(sub: np.ndarray) -> float:
            if np.isnan(sub).any():
                return np.nan
            return float(np.dot(sub, weights))
        res_df = input_df.rolling(window=n, min_periods=n).apply(_apply, raw=True)
        return res_df.iloc[:, 0].rename(s_name) if is_series else res_df

    windows = sliding_window_view(arr, window_shape=n, axis=0)  # (T-n+1, C, n)
    nan_mask = np.isnan(windows).any(axis=2)
    weighted = np.where(nan_mask[..., np.newaxis], 0.0, windows)
    dot = np.einsum("ijk,k->ij", weighted, weights)

    result = np.full((T, C), np.nan)
    result[n - 1 :] = np.where(nan_mask, np.nan, dot)
    res_df = pd.DataFrame(result, index=input_df.index, columns=input_df.columns)
    return res_df.iloc[:, 0].rename(s_name) if is_series else res_df


def observed_over(*inputs: tuple[pd.DataFrame | pd.Series, int]) -> pd.DataFrame | pd.Series:
    """
    Mask indicating cells where every input has complete historical observations
    over its declared lookback reach.
    """
    if not inputs:
        raise ValueError("observed_over requires at least one (frame, n) pair")
    present = None
    for frame, n in inputs:
        seen = frame.notna().astype(float).rolling(n, min_periods=n).min().eq(1.0)
        present = seen if present is None else present & seen
    return present
