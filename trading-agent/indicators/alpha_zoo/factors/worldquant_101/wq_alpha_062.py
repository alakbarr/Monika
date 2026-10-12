# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_062.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_062
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_062
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_062 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_062',
    'nickname': 'Kakushadze Alpha #62',
    'theme': ['volume'],
    'formula_latex': '(rank(correlation(vwap, sum(adv20,22), 10)) < rank(((rank(open)+rank(open)) < (rank((high+low)/2)+rank(high))))) * -1',
    'columns_required': ['open', 'high', 'low', 'volume', 'vwap', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 35,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_062 import (
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
