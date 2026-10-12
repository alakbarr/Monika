# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_032.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_032
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_032
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_032 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_032',
    'nickname': 'Kakushadze Alpha #32',
    'theme': ['momentum'],
    'formula_latex': 'scale(sum(close,7)/7 - close) + 20*scale(correlation(vwap, delay(close,5), 230))',
    'columns_required': ['close', 'vwap'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 235,
    'notes': 'Very long lookback (>= ~100 bars); produces NaN warmup on short panels which may trigger the >95% NaN registry guard.',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_032 import (
    ALPHA_ID,
    _delay,
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
