
"""GTJA Alpha #53.

Formula: COUNT(CLOSE>DELAY(CLOSE,1),12)/12*100
Source: Guotai Junan Securities 191 Alpha Research (2014), alpha 53."""

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
    "id": "gtja191_053",
    "theme": ['momentum'],
    "formula_latex": 'COUNT(CLOSE>DELAY(CLOSE,1),12)/12*100',
    "columns_required": ['close'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 12,
    "min_warmup_bars": 13,
    "notes": 'Pct of up-days in 12d window.',
}

def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    c = panel["close"]
    # A missing close or prior close is not a down day (#1463).
    up = (c > c.shift(1)).astype(float).where(c.notna() & c.shift(1).notna())
    return up.rolling(12, min_periods=12).sum() / 12.0 * 100.0