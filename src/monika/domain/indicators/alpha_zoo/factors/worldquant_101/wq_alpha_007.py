"""Kakushadze Alpha #7.

Formula (paper appendix): (adv20<volume)?((-1*ts_rank(abs(delta(close,7)),60))*sign(delta(close,7))):(-1)
Source: Kakushadze (2015), "101 Formulaic Alphas", arXiv:1601.00991, eq. 7.
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

ALPHA_ID = "alpha101_007"

__alpha_meta__ = {
    "id": "alpha101_007",
    "nickname": "Kakushadze Alpha #7",
    "theme": ["momentum", "volume"],
    "formula_latex": "(adv20<volume)?((-1*ts_rank(abs(delta(close,7)),60))*sign(delta(close,7))):(-1)",
    "columns_required": ["close", "volume"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_us", "equity_in", "equity_kr"],
    "frequency": ["1D"],
    "decay_horizon": 5,
    "min_warmup_bars": 67,
    "notes": "",
}


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
    adv20 = ts_mean(volume, 20)

    # Helper aliases (local closures keep the file standalone & purity-safe).
    make_one = _make_one
    where_ternary = _where_ternary
    d7 = delta(close, 7)
    expr = (-1.0 * ts_rank(d7.abs(), 60)) * np.sign(d7)
    out = where_ternary(adv20 < volume, expr, -1.0 * make_one(close))
    # A NaN comparison is False, not NaN, so where_ternary's own
    # np.isfinite safety net never fires here: the else branch is a
    # constant with no NaN dependency, so it stays finite well before
    # adv20's 20-day lookback is available, fabricating a signal during
    # the declared warmup instead of NaN.
    return out.where(adv20.notna())
