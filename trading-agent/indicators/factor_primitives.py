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


def safe_div(
    a: pd.DataFrame | pd.Series | np.ndarray | float,
    b: pd.DataFrame | pd.Series | np.ndarray | float,
    eps: float = 1e-12,
) -> pd.DataFrame | pd.Series | np.ndarray | float:
    """
    Division with zero/NaN guards: a / (b + eps * sign(b)).
    
    If b is exactly 0.0 or NaN, the result is strictly NaN (never +/- inf or silent 0).
    """
    if isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame):
        a_f = _as_float(a)
        b_f = _as_float(b)
        b_arr = b_f.to_numpy(dtype=np.float64, na_value=np.nan)
        sign = np.where(b_arr == 0.0, 1.0, np.sign(b_arr))
        denom_arr = b_arr + eps * sign
        denom = pd.DataFrame(denom_arr, index=b_f.index, columns=b_f.columns)
        res = a_f.div(denom)
        res = res.where(b_f != 0.0, np.nan)
        return res.replace([np.inf, -np.inf], np.nan)
    
    if isinstance(a, pd.Series) and isinstance(b, pd.Series):
        a_f = _as_float(a)
        b_f = _as_float(b)
        b_arr = b_f.to_numpy(dtype=np.float64, na_value=np.nan)
        sign = np.where(b_arr == 0.0, 1.0, np.sign(b_arr))
        denom = pd.Series(b_arr + eps * sign, index=b_f.index)
        res = a_f / denom
        res = res.where(b_f != 0.0, np.nan)
        return res.replace([np.inf, -np.inf], np.nan)
    
    arr_a = np.asarray(a, dtype=np.float64)
    arr_b = np.asarray(b, dtype=np.float64)
    sign = np.sign(arr_b)
    denom = arr_b + eps * sign
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.where(arr_b == 0.0, np.nan, arr_a / denom)
    res = np.where(np.isinf(res), np.nan, res)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(res) if not np.isnan(res) else np.nan
    return res


def rank(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cross-sectional percentile rank across columns (axis=1, average ties).
    Returns values in range (0.0, 1.0]. NaN values are strictly preserved.
    """
    return df.rank(axis=1, method="average", pct=True, na_option="keep")


def zscore(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cross-sectional z-score per row (axis=1, sample standard deviation ddof=1).
    Rows with zero variance or all NaNs become NaN (never silent 0).
    """
    df_f = _as_float(df)
    mean = df_f.mean(axis=1, skipna=True)
    std = df_f.std(axis=1, ddof=1, skipna=True)
    res = df_f.sub(mean, axis=0).div(std.where(std > 0), axis=0)
    return res.replace([np.inf, -np.inf], np.nan)


def scale(df: pd.DataFrame, a: float = 1.0) -> pd.DataFrame:
    """
    L1 normalization across row so sum of absolute values equals a.
    Rows with sum == 0 or all NaN become NaN.
    """
    df_f = _as_float(df)
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


def ts_rank(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Rolling time-series rank (percentile in [0, 1]) within an n-bar lookback window.
    Warmup rows (first n-1 rows per column) return NaN.
    Vectorized using numpy sliding_window_view for high throughput.
    """
    if n < 1:
        raise ValueError(f"ts_rank window must be >= 1, got {n}")

    arr = df.to_numpy(dtype=np.float64)
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
        return df.rolling(window=n, min_periods=n).apply(_last_rank, raw=True)

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
    return pd.DataFrame(result, index=df.index, columns=df.columns)


def ts_corr(x: pd.DataFrame, y: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Rolling Pearson correlation per column with min_periods=n.
    Constant series in window return NaN (no silent zero).
    """
    if n < 2:
        raise ValueError(f"ts_corr window must be >= 2, got {n}")
    x_f = _as_float(x)
    y_f = _as_float(y)
    cols = x_f.columns.union(y_f.columns)
    xa = x_f.reindex(columns=cols)
    ya = y_f.reindex(columns=cols)
    corr = xa.rolling(window=n, min_periods=n).corr(ya)
    return corr.replace([np.inf, -np.inf], np.nan)


def ts_cov(x: pd.DataFrame, y: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rolling sample covariance per column with min_periods=n."""
    if n < 2:
        raise ValueError(f"ts_cov window must be >= 2, got {n}")
    x_f = _as_float(x)
    y_f = _as_float(y)
    cols = x_f.columns.union(y_f.columns)
    xa = x_f.reindex(columns=cols)
    ya = y_f.reindex(columns=cols)
    cov = xa.rolling(window=n, min_periods=n).cov(ya)
    return cov.replace([np.inf, -np.inf], np.nan)


def ts_mean(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rolling arithmetic mean with strict warmup -> NaN."""
    if n < 1:
        raise ValueError(f"ts_mean window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).mean()


def ts_std(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rolling sample standard deviation (ddof=1) with warmup -> NaN."""
    if n < 2:
        raise ValueError(f"ts_std window must be >= 2, got {n}")
    return df.rolling(window=n, min_periods=n).std(ddof=1)


def ts_max(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rolling maximum per column with warmup -> NaN."""
    if n < 1:
        raise ValueError(f"ts_max window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).max()


def ts_min(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rolling minimum per column with warmup -> NaN."""
    if n < 1:
        raise ValueError(f"ts_min window must be >= 1, got {n}")
    return df.rolling(window=n, min_periods=n).min()


def ts_argmax(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Rolling argmax returning 0-based index into the n-bar window.
    Warmup -> NaN. Uses Bottleneck move_argmax if available, else numpy sliding window.
    """
    if n < 1:
        raise ValueError(f"ts_argmax window must be >= 1, got {n}")
    if HAS_BOTTLENECK and bn is not None:
        arr = df.to_numpy(dtype=np.float64)
        raw = bn.move_argmax(arr, window=n, min_count=n, axis=0)
        corrected = (n - 1) - raw
        return pd.DataFrame(corrected, index=df.index, columns=df.columns)

    def _argmax_last(sub: np.ndarray) -> float:
        if np.isnan(sub).all():
            return np.nan
        filled = np.where(np.isnan(sub), -np.inf, sub)
        return float(np.argmax(filled))

    return df.rolling(window=n, min_periods=n).apply(_argmax_last, raw=True)


def ts_argmin(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Rolling argmin returning 0-based index into the n-bar window.
    Warmup -> NaN. Uses Bottleneck move_argmin if available, else numpy sliding window.
    """
    if n < 1:
        raise ValueError(f"ts_argmin window must be >= 1, got {n}")
    if HAS_BOTTLENECK and bn is not None:
        arr = df.to_numpy(dtype=np.float64)
        raw = bn.move_argmin(arr, window=n, min_count=n, axis=0)
        corrected = (n - 1) - raw
        return pd.DataFrame(corrected, index=df.index, columns=df.columns)

    def _argmin_last(sub: np.ndarray) -> float:
        if np.isnan(sub).all():
            return np.nan
        filled = np.where(np.isnan(sub), np.inf, sub)
        return float(np.argmin(filled))

    return df.rolling(window=n, min_periods=n).apply(_argmin_last, raw=True)


def decay_linear(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Linear decay-weighted moving average with weights n, n-1, ..., 1 normalized.
    Vectorized using sliding_window_view and tensor contraction einsum.
    Warmup (first n-1 rows) -> NaN. Any NaN in the window propagates to NaN.
    """
    if n < 1:
        raise ValueError(f"decay_linear window must be >= 1, got {n}")
    weights = np.arange(1, n + 1, dtype=np.float64)
    weights /= weights.sum()

    arr = df.to_numpy(dtype=np.float64)
    T, C = arr.shape
    if T < n:
        def _apply(sub: np.ndarray) -> float:
            if np.isnan(sub).any():
                return np.nan
            return float(np.dot(sub, weights))
        return df.rolling(window=n, min_periods=n).apply(_apply, raw=True)

    windows = sliding_window_view(arr, window_shape=n, axis=0)  # (T-n+1, C, n)
    nan_mask = np.isnan(windows).any(axis=2)
    weighted = np.where(nan_mask[..., np.newaxis], 0.0, windows)
    dot = np.einsum("ijk,k->ij", weighted, weights)

    result = np.full((T, C), np.nan)
    result[n - 1 :] = np.where(nan_mask, np.nan, dot)
    return pd.DataFrame(result, index=df.index, columns=df.columns)


def observed_over(*inputs: tuple[pd.DataFrame, int]) -> pd.DataFrame:
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
