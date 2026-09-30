
"""GTJA Alpha #66.

Formula: (CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6)*100
Source: Guotai Junan Securities 191 Alpha Research (2014), alpha 66."""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.factor_primitives import (
    decay_linear,
    delta,
    rank,
    safe_div,
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

__alpha_meta__ = {
    "id": "gtja191_066",
    "theme": ['reversal'],
    "formula_latex": '(CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6)*100',
    "columns_required": ['close'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 6,
    "min_warmup_bars": 7,
    "notes": 'Bias-6 pct.',
}

def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    c = panel["close"]
    m6 = ts_mean(c, 6)
    return safe_div(c - m6, m6) * 100.0