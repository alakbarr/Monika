# Adapted from microsoft/qlib@d5379c520f66a39953bad76234a7019a72796fd0:qlib/contrib/data/handler.py
# (Apache-2.0). Copyright (c) Microsoft Corporation.
"""qlib158 IMIN5: formula = \\mathrm{ts\\_argmin}(\\mathrm{low}, 5) / 5."""
from __future__ import annotations

import pandas as pd
from indicators.factor_primitives import ts_argmin

__alpha_meta__ = {
    'id': 'qlib158_imin5',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_argmin}(\\\\mathrm{low}, 5) / 5',
    'columns_required': ['low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 5,
    'min_warmup_bars': 5,
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Return qlib158 IMIN5 on the supplied OHLCV panel."""
    lo = panel['low']
    return ts_argmin(lo, 5) / float(5)