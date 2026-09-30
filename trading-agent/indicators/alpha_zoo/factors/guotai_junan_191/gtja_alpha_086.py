
"""GTJA Alpha #86.

Formula: ((0.25 < (((DELAY(CLOSE,20)-DELAY(CLOSE,10))/10) - ((DELAY(CLOSE,10)-CLOSE)/10))) ? -1 : (((((DELAY(CLOSE,20)-DELAY(CLOSE,10))/10) - ((DELAY(CLOSE,10)-CLOSE)/10)) < 0) ? 1 : (-1*(CLOSE-DELAY(CLOSE,1)))))
Source: Guotai Junan Securities 191 Alpha Research (2014), alpha 86."""

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
    "id": "gtja191_086",
    "theme": ['momentum'],
    "formula_latex": '((0.25 < (((DELAY(CLOSE,20)-DELAY(CLOSE,10))/10) - ((DELAY(CLOSE,10)-CLOSE)/10))) ? -1 : (((((DELAY(CLOSE,20)-DELAY(CLOSE,10))/10) - ((DELAY(CLOSE,10)-CLOSE)/10)) < 0) ? 1 : (-1*(CLOSE-DELAY(CLOSE,1)))))',
    "columns_required": ['close'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 20,
    "min_warmup_bars": 22,
    "notes": 'Returns -1 / +1 / -delta depending on second-derivative thresholds.',
}

def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    c = panel["close"]
    a = (c.shift(20) - c.shift(10)) / 10.0
    b = (c.shift(10) - c) / 10.0
    diff = a - b
    last = -1.0 * (c - c.shift(1))
    out = pd.DataFrame(np.where(0.25 < diff, -1.0,
                                np.where(diff < 0, 1.0, last.to_numpy())),
                       index=c.index, columns=c.columns)
    # NaN comparisons are False, not NaN, so a gap that leaves diff
    # undefined (warmup, or a halt inside the 10/20-day lookback) would
    # otherwise fall through to the finite `last` branch instead of NaN.
    return out.where(diff.notna())