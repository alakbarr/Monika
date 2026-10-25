"""Microstructure Volume Price Rank Divergence Alpha.

Formula: -corr(rank(delta(ln(Vol))), rank((C - O) / O), 6)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from monika.domain.indicators.factor_primitives import delta, safe_div

__alpha_meta__ = {
    "id": "microstructure_volume_price_rank_divergence",
    "name": "microstructure_volume_price_rank_divergence",
    "nickname": "Volume-Price Rank Divergence Correlation",
    "category": "microstructure",
    "theme": ["microstructure"],
    "formula_latex": r"-\text{corr}(\text{rank}(\Delta \ln(\text{Vol})), \text{rank}(\frac{C-O}{O}), 6)",
    "columns_required": ["close", "open", "volume"],
    "lookback": 6,
    "min_warmup_bars": 6,
    "decay_horizon": 3,
    "direction": "positive_bullish",
    "description": "Identifies volume-price divergence: Unbacked price advances forecast mean-reverting retracements.",
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute Volume Price Rank Divergence."""
    cl = panel["close"]
    op = panel["open"]
    vol = panel["volume"]

    delta_log_vol = delta(np.log(vol + 1.0), 1)
    intraday_ret = safe_div(cl - op, op)

    # Rolling correlation between volume change rank and price change rank
    r_vol = delta_log_vol.rolling(6).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    r_ret = intraday_ret.rolling(6).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)

    corr = r_vol.rolling(6).corr(r_ret)
    return -corr
