"""Microstructure Range Dispersion Alpha.

Formula: (H - L) / SMA(H - L, 10) - 1.0
"""

from __future__ import annotations

import pandas as pd

from monika.domain.indicators.factor_primitives import safe_div

__alpha_meta__ = {
    "id": "microstructure_range_dispersion",
    "name": "microstructure_range_dispersion",
    "nickname": "Intraday High-Low Range Dispersion",
    "category": "volatility",
    "theme": ["volatility"],
    "formula_latex": r"\frac{H - L}{\text{SMA}(H - L, 10)} - 1.0",
    "columns_required": ["high", "low", "close"],
    "lookback": 10,
    "min_warmup_bars": 10,
    "decay_horizon": 4,
    "direction": "positive_bearish",
    "description": "Relative intraday candle spread normalized against its 10-period moving average.",
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute Range Dispersion."""
    high = panel["high"]
    low = panel["low"]
    candle_range = high - low
    avg_range = candle_range.rolling(10, min_periods=3).mean()
    return safe_div(candle_range, avg_range) - 1.0
