# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_095.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_095
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_095
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_095 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_095',
    'nickname': 'Kakushadze Alpha #95',
    'theme': ['volume'],
    'formula_latex': 'rank(open-ts_min(open,13)) < Ts_Rank((rank(correlation(sum((high+low)/2,19), sum(adv40,19),13))^5), 12)',
    'columns_required': ['open', 'high', 'low', 'volume', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 63,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_095 import (
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
