# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_073.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_073
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_073
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_073 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_073',
    'nickname': 'Kakushadze Alpha #73',
    'theme': ['volume'],
    'formula_latex': 'max(rank(decay_linear(delta(vwap,5), 3)), Ts_Rank(decay_linear(-1*(delta(0.147*open+0.853*low,2)/(0.147*open+0.853*low)), 3), 17)) * -1',
    'columns_required': ['open', 'low', 'vwap', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 21,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_073 import (
    ALPHA_ID,
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
