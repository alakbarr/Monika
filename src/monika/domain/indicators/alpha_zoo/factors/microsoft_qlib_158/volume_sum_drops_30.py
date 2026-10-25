# Adapted from microsoft/qlib@d5379c520f66a39953bad76234a7019a72796fd0:qlib/contrib/data/handler.py
# (Apache-2.0). Copyright (c) Microsoft Corporation.
"""qlib158 VSUMD30: formula = \\mathrm{VSUMP}_w - \\mathrm{VSUMN}_w."""

from __future__ import annotations

import pandas as pd

from monika.domain.indicators.factor_primitives import safe_div, ts_sum

__alpha_meta__ = {
    "id": "qlib158_vsumd30",
    "theme": ["volume", "volatility"],
    "formula_latex": "\\\\mathrm{VSUMP}_w - \\\\mathrm{VSUMN}_w",
    "columns_required": ["volume"],
    "universe": ["equity_us", "equity_cn", "equity_hk", "equity_in", "equity_kr"],
    "frequency": ["1d"],
    "decay_horizon": 30,
    "min_warmup_bars": 30,
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Return qlib158 VSUMD30 on the supplied OHLCV panel."""
    v = panel["volume"]
    diff = v - v.shift(1)
    pos = diff.where(diff > 0, 0.0)
    neg = (-diff).where(diff < 0, 0.0)
    absd = diff.abs()
    num_p = ts_sum(pos, 30)
    num_n = ts_sum(neg, 30)
    den = ts_sum(absd, 30)
    return safe_div(num_p - num_n, den)
