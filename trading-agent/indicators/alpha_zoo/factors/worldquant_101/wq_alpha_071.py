# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_071.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_071
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_071
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_071 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_071',
    'nickname': 'Kakushadze Alpha #71',
    'theme': ['volume', 'reversal'],
    'formula_latex': 'max(Ts_Rank(decay_linear(correlation(Ts_Rank(close,3), Ts_Rank(adv180,12), 18), 4), 16), Ts_Rank(decay_linear((rank((low+open)-(2*vwap))^2, 16), 4))',
    'columns_required': ['open', 'low', 'close', 'volume', 'vwap'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 226,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_071 import (
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
