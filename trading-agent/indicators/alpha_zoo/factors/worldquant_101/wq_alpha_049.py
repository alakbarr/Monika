# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_049.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_049
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_049
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_049 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_049',
    'nickname': 'Kakushadze Alpha #49',
    'theme': ['momentum'],
    'formula_latex': '(((delay(close,20)-delay(close,10))/10 - (delay(close,10)-close)/10) < -0.1) ? 1 : -1*(close-delay(close,1))',
    'columns_required': ['close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 21,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_049 import (
    ALPHA_ID,
    _delay,
    _make_one,
    _where_ternary,
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
    "_delay",
    "_make_one",
    "_where_ternary",
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
