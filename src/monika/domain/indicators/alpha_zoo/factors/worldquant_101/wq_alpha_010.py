
"""Kakushadze Alpha #10.

Formula (paper appendix): rank((0<ts_min(delta(close,1),4))?delta(close,1):((ts_max(delta(close,1),4)<0)?delta(close,1):(-1*delta(close,1))))
Source: Kakushadze (2015), "101 Formulaic Alphas", arXiv:1601.00991, eq. 10.
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

ALPHA_ID = "alpha101_010"

__alpha_meta__ = {
    'id': 'alpha101_010',
    'nickname': 'Kakushadze Alpha #10',
    'theme': ['momentum'],
    'formula_latex': 'rank((0<ts_min(delta(close,1),4))?delta(close,1):((ts_max(delta(close,1),4)<0)?delta(close,1):(-1*delta(close,1))))',
    'columns_required': ['close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 5,
    'notes': '',
}


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
    where_ternary = _where_ternary
    d1 = delta(close, 1)
    min4 = ts_min(d1, 4)
    max4 = ts_max(d1, 4)
    cond1 = min4 > 0
    cond2 = max4 < 0
    inner = where_ternary(cond1, d1, where_ternary(cond2, d1, -1.0 * d1))
    # A NaN comparison is False, not NaN, so where_ternary's own
    # np.isfinite safety net never fires here: the innermost fallback
    # only needs a 1-day delta and stays finite well before the 4-day
    # lookback is available, fabricating a signal during warmup instead
    # of NaN. rank() preserves NaN, so masking inner is enough.
    inner = inner.where(min4.notna() & max4.notna())
    out = rank(inner)
    return out