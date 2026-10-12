# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_050.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_050
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_050
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_050 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_050',
    'nickname': 'Kakushadze Alpha #50',
    'theme': ['volume'],
    'formula_latex': '-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5)',
    'columns_required': ['volume', 'vwap', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 10,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_050 import (
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
