
"""GTJA Alpha #40.

Formula: SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:0),26)/SUM((CLOSE<=DELAY(CLOSE,1)?VOLUME:0),26)*100
Source: Guotai Junan Securities 191 Alpha Research (2014), alpha 40."""

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
    "id": "gtja191_040",
    "theme": ['volume'],
    "formula_latex": 'SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:0),26)/SUM((CLOSE<=DELAY(CLOSE,1)?VOLUME:0),26)*100',
    "columns_required": ['close', 'volume'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 26,
    "min_warmup_bars": 27,
    "notes": 'Up-volume vs down-volume ratio over 26 days.',
}

def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    c = panel["close"]
    v = panel["volume"]
    pc = c.shift(1)
    up = c > pc
    # A bar whose close or prior close is missing is neither an up nor a down day (#1463).
    valid = c.notna() & pc.notna()
    up_v = v.where(up, 0.0).where(valid).rolling(26, min_periods=26).sum()
    dn_v = v.where(~up, 0.0).where(valid).rolling(26, min_periods=26).sum()
    return safe_div(up_v, dn_v) * 100.0