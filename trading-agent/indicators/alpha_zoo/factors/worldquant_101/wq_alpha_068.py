# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_068.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_068
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_068
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_068 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_068',
    'nickname': 'Kakushadze Alpha #68',
    'theme': ['volume'],
    'formula_latex': '(Ts_Rank(correlation(rank(high), rank(adv15), 9), 14) < rank(delta(0.518*close+0.482*low, 1))) * -1',
    'columns_required': ['high', 'low', 'close', 'volume'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 36,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_068 import (
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
