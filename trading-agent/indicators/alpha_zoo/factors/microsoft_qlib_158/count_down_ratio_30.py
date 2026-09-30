# Adapted from microsoft/qlib@d5379c520f66a39953bad76234a7019a72796fd0:qlib/contrib/data/handler.py
# (Apache-2.0). Copyright (c) Microsoft Corporation.
"""qlib158 CNTD30: formula = \\mathrm{CNTP}_30 - \\mathrm{CNTN}_30."""
from __future__ import annotations

import pandas as pd

__alpha_meta__ = {
    'id': 'qlib158_cntd30',
    'theme': ['reversal'],
    'formula_latex': '\\\\mathrm{CNTP}_30 - \\\\mathrm{CNTN}_30',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 30,
    'min_warmup_bars': 30,
    'notes': 'A missing close leaves window+1 rolling rows NaN; on sparse panels this can trigger the >95% NaN registry guard (from ~10% missing bars).',
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Return qlib158 CNTD30 on the supplied OHLCV panel."""
    c = panel['close']
    prev = c.shift(1)
    up = (c > prev).astype('float64').where(c.notna() & prev.notna())  # a missing close is not an up day
    dn = (c < prev).astype('float64').where(c.notna() & prev.notna())  # ...nor a down day
    up_w = up.rolling(window=30, min_periods=30).mean()
    dn_w = dn.rolling(window=30, min_periods=30).mean()
    return up_w - dn_w