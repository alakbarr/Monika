# Adapted from microsoft/qlib@d5379c520f66a39953bad76234a7019a72796fd0:qlib/contrib/data/handler.py
# (Apache-2.0). Copyright (c) Microsoft Corporation.
"""qlib158 MIN20: formula = \\mathrm{ts\\_min}(\\mathrm{low}, 20) / \\mathrm{close}."""
from __future__ import annotations

import pandas as pd
from indicators.factor_primitives import safe_div, ts_min

__alpha_meta__ = {
    'id': 'qlib158_min20',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_min}(\\\\mathrm{low}, 20) / \\\\mathrm{close}',
    'columns_required': ['low', 'close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 20,
    'min_warmup_bars': 20,
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Return qlib158 MIN20 on the supplied OHLCV panel."""
    lo = panel['low']
    c = panel['close']
    return safe_div(ts_min(lo, 20), c)