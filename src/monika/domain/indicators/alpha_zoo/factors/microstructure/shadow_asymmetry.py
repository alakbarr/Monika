"""Microstructure Shadow Asymmetry Alpha.

Formula: (LowerShadow - UpperShadow) / (High - Low)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from monika.domain.indicators.factor_primitives import safe_div

__alpha_meta__ = {
    "id": "microstructure_shadow_asymmetry",
    "name": "microstructure_shadow_asymmetry",
    "nickname": "Candlestick Shadow Asymmetry Reversal",
    "category": "mean_reversion",
    "theme": ["mean_reversion"],
    "formula_latex": r"\frac{\text{LowerShadow} - \text{UpperShadow}}{\text{High} - \text{Low}}",
    "columns_required": ["open", "high", "low", "close"],
    "lookback": 5,
    "min_warmup_bars": 5,
    "decay_horizon": 2,
    "direction": "positive_bullish",
    "description": "Calculates rejection shadow asymmetry: Long lower wicks indicate institutional absorption and support.",
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute Shadow Asymmetry."""
    op = panel["open"]
    hi = panel["high"]
    lo = panel["low"]
    cl = panel["close"]

    candle_range = hi - lo
    body_high = np.maximum(op, cl)
    body_low = np.minimum(op, cl)

    upper_shadow = hi - body_high
    lower_shadow = body_low - lo

    asymmetry = safe_div(lower_shadow - upper_shadow, candle_range)
    return asymmetry.rolling(5, min_periods=1).mean()
