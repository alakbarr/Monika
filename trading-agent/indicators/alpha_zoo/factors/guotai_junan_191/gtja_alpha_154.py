
"""GTJA Alpha 154 ( 191  alpha , 2014).

Formula (verbatim from the report):
    (((VWAP - MIN(VWAP,16))) < (CORR(VWAP, MEAN(VOLUME,180),18))) cast to float * -1 (binary indicator)

Notes: Original returns boolean; we cast to float and multiply by -1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.factor_primitives import (
    decay_linear,
    delta,
    observed_over,
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
    vwap,
)

ALPHA_ID = "gtja191_154"

__alpha_meta__ = {
    'id': 'gtja191_154',
    'theme': ['volume'],
    'formula_latex': 'see body',
    'columns_required': ['open', 'high', 'low', 'close', 'volume', 'amount'],
    'extras_required': [],
    'universe': ['equity_cn'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 198,
    'notes': 'Original returns boolean; we cast to float and multiply by -1.',
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute gtja191_154.

    Args:
        panel: dict[str, pd.DataFrame] with at least the required columns.

    Returns:
        pd.DataFrame with index = panel["close"].index, columns = panel["close"].columns.
    """
    v = panel["volume"]
    vw = vwap(panel, "equity_cn")

    left = vw - ts_min(vw, 16)
    right = ts_corr(vw, ts_mean(v, 180), 18)
    out = (left < right).astype("float64") * -1.0
    # Reach of each input through the nested windows; a gap inside it is not a verdict (#1463).
    # v: mean 180 + corr 18; vw: corr 18.
    return out.where(observed_over((v, 197), (vw, 18)))