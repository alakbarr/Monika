"""Kakushadze Alpha #27.

Formula (paper appendix): (0.5<rank((sum(correlation(rank(volume),rank(vwap),6),2)/2.0)))?(-1):1
Source: Kakushadze (2015), "101 Formulaic Alphas", arXiv:1601.00991, eq. 27.
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from monika.domain.indicators.factor_primitives import (
    decay_linear,
    delta,
    rank,
    safe_div,
    scale,
    signed_power,
    ts_argmax,
    ts_argmin,
    ts_corr,
    ts_cov,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
)

ALPHA_ID = "alpha101_027"

__alpha_meta__ = {
    "id": "alpha101_027",
    "nickname": "Kakushadze Alpha #27",
    "theme": ["volume"],
    "formula_latex": "(0.5<rank((sum(correlation(rank(volume),rank(vwap),6),2)/2.0)))?(-1):1",
    "columns_required": ["volume", "vwap", "close"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_us", "equity_in", "equity_kr"],
    "frequency": ["1D"],
    "decay_horizon": 5,
    "min_warmup_bars": 10,
    "notes": "",
}


def _rolling_sum(df: Any, n: int) -> Any:
    """Rolling window sum; warmup -> NaN."""
    if n < 1:
        raise ValueError("rolling_sum requires n >= 1")
    return df.rolling(window=n, min_periods=n).sum()


def _make_one(ref: Any) -> Any:
    """A Series or DataFrame of 1.0 with the same shape/index as ref."""
    if isinstance(ref, pd.Series):
        return pd.Series(1.0, index=ref.index, name=ref.name)
    if isinstance(ref, pd.DataFrame):
        return pd.DataFrame(1.0, index=ref.index, columns=ref.columns)
    return np.ones_like(ref, dtype=np.float64)


def _where_ternary(cond: Any, a: Any, b: Any) -> Any:
    """Vectorised ternary `(cond ? a : b)` returning DataFrame or Series."""
    cond_arr = cond.to_numpy(dtype=bool, na_value=False) if hasattr(cond, "to_numpy") else np.asarray(cond, dtype=bool)
    if isinstance(a, (int, float)):
        a_arr = np.full_like(cond_arr, float(a), dtype=np.float64)
    elif hasattr(a, "to_numpy"):
        a_arr = a.to_numpy(dtype=np.float64, na_value=np.nan)
    else:
        a_arr = np.asarray(a, dtype=np.float64)

    if isinstance(b, (int, float)):
        b_arr = np.full_like(cond_arr, float(b), dtype=np.float64)
    elif hasattr(b, "to_numpy"):
        b_arr = b.to_numpy(dtype=np.float64, na_value=np.nan)
    else:
        b_arr = np.asarray(b, dtype=np.float64)

    out = np.where(cond_arr, a_arr, b_arr)
    out = np.where(np.isfinite(out), out, np.nan)
    target = cond if hasattr(cond, "index") else (a if hasattr(a, "index") else b)
    if isinstance(target, pd.Series):
        return pd.Series(out, index=target.index, name=target.name)
    if isinstance(target, pd.DataFrame):
        return pd.DataFrame(out, index=target.index, columns=target.columns)
    return out


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute the alpha on the OHLCV+ panel and return a wide DataFrame."""
    close = panel["close"]
    volume = panel["volume"]
    vwap = panel["vwap"]

    # Helper aliases (local closures keep the file standalone & purity-safe).
    rolling_sum = _rolling_sum
    make_one = _make_one
    where_ternary = _where_ternary
    x = rank(rolling_sum(ts_corr(rank(volume), rank(vwap), 6), 2) / 2.0)
    out = where_ternary(x > 0.5, -1.0 * make_one(close), make_one(close))
    # A NaN comparison is False, not NaN, so where_ternary's own
    # np.isfinite safety net never fires here: both branches are pure
    # constants with no NaN dependency at all, so the chain stays finite
    # through warmup instead of NaN.
    return out.where(x.notna())
