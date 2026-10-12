# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_045.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_045
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_045
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_045 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_045',
    'nickname': 'Kakushadze Alpha #45',
    'theme': ['momentum', 'volume'],
    'formula_latex': '-1 * (rank(sum(delay(close,5),20)/20)*correlation(close,volume,2)*rank(correlation(sum(close,5),sum(close,20),2)))',
    'columns_required': ['close', 'volume'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 25,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_045 import (
    ALPHA_ID,
    _delay,
    _rolling_sum,
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
    "_rolling_sum",
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
