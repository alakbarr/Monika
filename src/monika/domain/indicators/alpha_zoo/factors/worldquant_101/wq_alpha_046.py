"""Kakushadze Alpha #46.

Formula (paper appendix): complex piecewise; see paper
Source: Kakushadze (2015), "101 Formulaic Alphas", arXiv:1601.00991, eq. 46.
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

ALPHA_ID = "alpha101_046"

__alpha_meta__ = {
    "id": "alpha101_046",
    "nickname": "Kakushadze Alpha #46",
    "theme": ["momentum"],
    "formula_latex": "complex piecewise; see paper",
    "columns_required": ["close"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_us", "equity_in", "equity_kr"],
    "frequency": ["1D"],
    "decay_horizon": 5,
    "min_warmup_bars": 21,
    "notes": "",
}


def _delay(df: Any, n: int) -> Any:
    """Backward shift by n (lookahead-safe; n>=1 required)."""
    if n < 1:
        raise ValueError("delay requires n >= 1 (lookahead ban)")
    return df.shift(n)


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

    # Helper aliases (local closures keep the file standalone & purity-safe).
    delay = _delay
    make_one = _make_one
    where_ternary = _where_ternary
    x = ((delay(close, 20) - delay(close, 10)) / 10.0) - ((delay(close, 10) - close) / 10.0)
    one = make_one(close)
    out = where_ternary(0.25 < x, -1.0 * one, where_ternary(x < 0.0, one, -1.0 * (close - delay(close, 1))))
    # A NaN comparison is False, not NaN, so where_ternary's own
    # np.isfinite safety net never fires here: the innermost fallback
    # only needs a 1-day delay and stays finite well before x's 20-day
    # lookback is available, fabricating a signal during warmup instead
    # of NaN.
    return out.where(x.notna())
