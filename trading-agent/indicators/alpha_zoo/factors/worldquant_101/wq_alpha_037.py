# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_037.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_037
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_037
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_037 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_037',
    'nickname': 'Kakushadze Alpha #37',
    'theme': ['momentum'],
    'formula_latex': 'rank(correlation(delay(open-close,1),close,200)) + rank(open-close)',
    'columns_required': ['open', 'close'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 201,
    'notes': 'Very long lookback (>= ~100 bars); produces NaN warmup on short panels which may trigger the >95% NaN registry guard.',
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_037 import (
    ALPHA_ID,
    _delay,
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
