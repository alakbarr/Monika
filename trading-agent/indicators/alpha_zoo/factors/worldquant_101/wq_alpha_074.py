# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_074.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_074
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_074
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_074 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_074',
    'nickname': 'Kakushadze Alpha #74',
    'theme': ['volume'],
    'formula_latex': '(rank(correlation(close, sum(adv30,37), 15)) < rank(correlation(rank(0.026*high+0.974*vwap), rank(volume), 11))) * -1',
    'columns_required': ['high', 'close', 'volume', 'vwap'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 60,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_074 import (
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
