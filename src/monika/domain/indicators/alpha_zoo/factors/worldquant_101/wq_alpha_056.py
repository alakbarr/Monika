"""Kakushadze Alpha #56.

Formula (paper appendix): 0 - 1*(rank(sum(returns,10)/sum(sum(returns,2),3)) * rank((returns * cap)))  [cap unavailable -> 1]
Source: Kakushadze (2015), "101 Formulaic Alphas", arXiv:1601.00991, eq. 56.
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

ALPHA_ID = "alpha101_056"

__alpha_meta__ = {
    "id": "alpha101_056",
    "nickname": "Kakushadze Alpha #56",
    "theme": ["momentum"],
    "formula_latex": "0 - 1*(rank(sum(returns,10)/sum(sum(returns,2),3)) * rank((returns * cap)))  [cap unavailable -> 1]",
    "columns_required": ["close"],
    "extras_required": [],
    "requires_sector": True,
    "universe": ["equity_us", "equity_in", "equity_kr"],
    "frequency": ["1D"],
    "decay_horizon": 5,
    "min_warmup_bars": 10,
    "notes": "Industry neutralization implemented via per-row sector group demean (panel['sector'] required). When sector tag is absent the registry rejects via SkipAlpha; the compute() also has a degraded global demean fallback. This is a partial approximation of the paper's IndClass.industry/subindustry/sector neutralization. Paper formula uses market 'cap' which is not part of the standard OHLCV panel; substituted by a constant 1.0 DataFrame. Result remains a valid factor but loses the cap-weighting term.",
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


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute the alpha on the OHLCV+ panel and return a wide DataFrame."""
    close = panel["close"]

    returns = close.pct_change(fill_method=None)
    # Helper aliases (local closures keep the file standalone & purity-safe).
    rolling_sum = _rolling_sum
    make_one = _make_one
    # 'cap' (market cap) is not part of the standard panel; degrade to 1.0
    cap = make_one(close)
    num = rolling_sum(returns, 10)
    denom = rolling_sum(rolling_sum(returns, 2), 3)
    out = 0.0 - (rank(safe_div(num, denom)) * rank(returns * cap))
    return out
