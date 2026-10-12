# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_047.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_047
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_047
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_047 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_047',
    'nickname': 'Kakushadze Alpha #47',
    'theme': ['volume', 'momentum'],
    'formula_latex': '((rank(1/close)*volume/adv20) * (high*rank(high-close)/(sum(high,5)/5))) - rank(vwap-delay(vwap,5))',
    'columns_required': ['high', 'close', 'volume', 'vwap'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 25,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_047 import (
    ALPHA_ID,
    _delay,
    _make_one,
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
    "_make_one",
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
