# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_099.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_099
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_099
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_099 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_099',
    'nickname': 'Kakushadze Alpha #99',
    'theme': ['volume'],
    'formula_latex': '(rank(correlation(sum((high+low)/2, 20), sum(adv60, 20), 9)) < rank(correlation(low, volume, 6))) * -1',
    'columns_required': ['high', 'low', 'volume', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 68,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_099 import (
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
