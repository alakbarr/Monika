# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_086.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_086
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_086
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_086 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_086',
    'nickname': 'Kakushadze Alpha #86',
    'theme': ['volume'],
    'formula_latex': '(Ts_Rank(correlation(close, sum(adv20,15), 6), 20) < rank((open+close) - (vwap+open))) * -1',
    'columns_required': ['open', 'close', 'volume', 'vwap'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 44,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_086 import (
    ALPHA_ID,
    _rolling_sum,
    annotations,
    compute,
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
)

sys.modules[__name__] = _canonical

__all__ = [
    "ALPHA_ID",
    "_rolling_sum",
    "annotations",
    "compute",
    "decay_linear",
    "delta",
    "observed_over",
    "rank",
    "safe_div",
    "scale",
    "signed_power",
    "ts_argmax",
    "ts_argmin",
    "ts_corr",
    "ts_cov",
    "ts_max",
    "ts_mean",
    "ts_min",
    "ts_rank",
    "ts_std",
]
