# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_066.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_066
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_066
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_066 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_066',
    'nickname': 'Kakushadze Alpha #66',
    'theme': ['momentum'],
    'formula_latex': '(rank(decay_linear(delta(vwap,4), 7)) + Ts_Rank(decay_linear(((0.966*low+0.034*low - vwap)/(open-(high+low)/2)), 11), 7)) * -1',
    'columns_required': ['open', 'high', 'low', 'vwap', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 18,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_066 import (
    ALPHA_ID,
    annotations,
    compute,
    decay_linear,
    delta,
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
