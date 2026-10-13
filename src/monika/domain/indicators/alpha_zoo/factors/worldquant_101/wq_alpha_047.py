"""Kakushadze Alpha #47.

Formula (paper appendix): ((rank(1/close)*volume/adv20) * (high*rank(high-close)/(sum(high,5)/5))) - rank(vwap-delay(vwap,5))
Source: Kakushadze (2015), "101 Formulaic Alphas", arXiv:1601.00991, eq. 47.
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

ALPHA_ID = "alpha101_047"

__alpha_meta__ = {
    "id": "alpha101_047",
    "nickname": "Kakushadze Alpha #47",
    "theme": ["volume", "momentum"],
    "formula_latex": "((rank(1/close)*volume/adv20) * (high*rank(high-close)/(sum(high,5)/5))) - rank(vwap-delay(vwap,5))",
    "columns_required": ["high", "close", "volume", "vwap"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_us", "equity_in", "equity_kr"],
    "frequency": ["1D"],
    "decay_horizon": 5,
    "min_warmup_bars": 25,
    "notes": "",
}


def _rolling_sum(df: Any, n: int) -> Any:
    """Rolling window sum; warmup -> NaN."""
    if n < 1:
        raise ValueError("rolling_sum requires n >= 1")
    return df.rolling(window=n, min_periods=n).sum()


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


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute the alpha on the OHLCV+ panel and return a wide DataFrame."""
    close = panel["close"]
    high = panel["high"]
    volume = panel["volume"]
    vwap = panel["vwap"]
    adv20 = ts_mean(volume, 20)

    # Helper aliases (local closures keep the file standalone & purity-safe).
    rolling_sum = _rolling_sum
    delay = _delay
    make_one = _make_one
    t1 = safe_div(rank(safe_div(make_one(close), close)) * volume, adv20)
    t2 = safe_div(high * rank(high - close), rolling_sum(high, 5) / 5.0)
    out = t1 * t2 - rank(vwap - delay(vwap, 5))
    return out
