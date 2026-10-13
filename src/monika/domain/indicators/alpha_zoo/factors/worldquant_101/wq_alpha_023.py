
"""Kakushadze Alpha #23.

Formula (paper appendix): ((sum(high,20)/20) < high) ? (-1*delta(high,2)) : 0
Source: Kakushadze (2015), "101 Formulaic Alphas", arXiv:1601.00991, eq. 23.
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

ALPHA_ID = "alpha101_023"

__alpha_meta__ = {
    'id': 'alpha101_023',
    'nickname': 'Kakushadze Alpha #23',
    'theme': ['momentum'],
    'formula_latex': '((sum(high,20)/20) < high) ? (-1*delta(high,2)) : 0',
    'columns_required': ['high', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 20,
    'notes': '',
}


def _rolling_sum(df: Any, n: int) -> Any:
    """Rolling window sum; warmup -> NaN."""
    if n < 1:
        raise ValueError("rolling_sum requires n >= 1")
    return df.rolling(window=n, min_periods=n).sum()


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
    high = panel["high"]


    # Helper aliases (local closures keep the file standalone & purity-safe).
    rolling_sum = _rolling_sum
    where_ternary = _where_ternary
    mh = rolling_sum(high, 20) / 20.0
    out = where_ternary(mh < high, -1.0 * delta(high, 2), 0.0 * close)
    # A NaN comparison is False, not NaN, so where_ternary's own
    # np.isfinite safety net never fires here: the else branch is 0.0
    # times a finite close, so it stays finite well before mh's 20-day
    # lookback is available, fabricating a signal during warmup instead
    # of NaN.
    return out.where(mh.notna())