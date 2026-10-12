# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_092.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_092
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_092
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_092 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_092',
    'nickname': 'Kakushadze Alpha #92',
    'theme': ['volume'],
    'formula_latex': 'min(Ts_Rank(decay_linear(((high+low)/2 + close < low+open), 15), 19), Ts_Rank(decay_linear(correlation(rank(low), rank(adv30), 8), 7), 7))',
    'columns_required': ['open', 'high', 'low', 'close', 'volume'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 49,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_092 import (
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
