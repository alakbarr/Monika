# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_031.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_031
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_031
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_031 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_031',
    'nickname': 'Kakushadze Alpha #31',
    'theme': ['momentum'],
    'formula_latex': 'rank(rank(rank(decay_linear(-1*rank(rank(delta(close,10))),10)))) + rank(-1*delta(close,3)) + sign(scale(correlation(adv20,low,12)))',
    'columns_required': ['low', 'close', 'volume'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 25,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_031 import (
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
