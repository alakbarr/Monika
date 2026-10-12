# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_040.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_040
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_040
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_040 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_040',
    'nickname': 'Kakushadze Alpha #40',
    'theme': ['volatility', 'volume'],
    'formula_latex': '(-1*rank(stddev(high,10))) * correlation(high,volume,10)',
    'columns_required': ['high', 'volume', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 10,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_040 import (
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
