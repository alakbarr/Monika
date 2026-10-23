"""Microstructure Volume Weighted Momentum Alpha.

Formula: VWAP(5) / VWAP(14) - 1.0
"""

from __future__ import annotations

import pandas as pd

from monika.domain.indicators.factor_primitives import safe_div

__alpha_meta__ = {
    "id": "microstructure_volume_weighted_momentum",
    "name": "microstructure_volume_weighted_momentum",
    "nickname": "Volume-Weighted Momentum Surge",
    "category": "momentum",
    "theme": ["momentum"],
    "formula_latex": r"\frac{\text{SMA}(C \times \text{Vol}, 5)}{\text{SMA}(\text{Vol}, 5)} - \frac{\text{SMA}(C \times \text{Vol}, 14)}{\text{SMA}(\text{Vol}, 14)}",
    "columns_required": ["close", "volume"],
    "lookback": 14,
    "min_warmup_bars": 14,
    "decay_horizon": 5,
    "direction": "positive_bullish",
    "description": "VWAP crossover divergence measuring short-term volume-weighted velocity relative to medium-term baseline.",
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute Volume Weighted Momentum."""
    cl = pd.Series(panel["close"])
    vol = pd.Series(panel["volume"])
    pv = cl * vol
    vwap_fast = pd.Series(safe_div(pv.rolling(5).sum(), vol.rolling(5).sum()))
    vwap_slow = pd.Series(safe_div(pv.rolling(14).sum(), vol.rolling(14).sum()))
    return pd.Series(safe_div(vwap_fast - vwap_slow, vwap_slow))
