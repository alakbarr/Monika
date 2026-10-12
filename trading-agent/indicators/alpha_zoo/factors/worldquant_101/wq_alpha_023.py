# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_023.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_023
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_023
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_023 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_023',
    'nickname': 'Kakushadze Alpha #23',
    'theme': ['momentum'],
    'formula_latex': '((sum(high,20)/20) < high) ? (-1*delta(high,2)) : 0',
    'columns_required': ['high', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 20,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_023 import (
    ALPHA_ID,
    _rolling_sum,
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
    "_rolling_sum",
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
