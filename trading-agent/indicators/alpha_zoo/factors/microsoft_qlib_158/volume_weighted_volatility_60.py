# Adapted from microsoft/qlib@be725493eb1a6bbb42bf11b37aa7669f59610ff1:qlib/contrib/data/loader.py
# (MIT). Copyright (c) Microsoft Corporation.
"""qlib158 WVMA60: formula = \\mathrm{ts\\_std}(|\\mathrm{ret}|\\cdot v, 60) / \\mathrm{ts\\_mean}(|\\mathrm{ret}|\\cdot v, 60)."""
from __future__ import annotations

import pandas as pd
from indicators.factor_primitives import safe_div, ts_mean, ts_std

__alpha_meta__ = {
    'id': 'qlib158_wvma60',
    'theme': ['volume', 'volatility'],
    'formula_latex': '\\\\mathrm{ts\\\\_std}(|\\\\mathrm{ret}|\\\\cdot v, 60) / \\\\mathrm{ts\\\\_mean}(|\\\\mathrm{ret}|\\\\cdot v, 60)',
    'columns_required': ['close', 'volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Return qlib158 WVMA60 on the supplied OHLCV panel."""
    c = panel['close']
    v = panel['volume']
    ret = safe_div(c, c.shift(1)) - 1.0
    arv = ret.abs() * v
    return safe_div(ts_std(arv, 60), ts_mean(arv, 60))