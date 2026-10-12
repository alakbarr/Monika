# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_088.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_088
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_088
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_088 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_088',
    'nickname': 'Kakushadze Alpha #88',
    'theme': ['volume'],
    'formula_latex': 'min(rank(decay_linear((rank(open)+rank(low))-(rank(high)+rank(close)),8)), Ts_Rank(decay_linear(correlation(Ts_Rank(close,8),Ts_Rank(adv60,20),8),7),3))',
    'columns_required': ['open', 'high', 'low', 'close', 'volume'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 94,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_088 import (
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
