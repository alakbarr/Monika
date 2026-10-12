# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_084.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_084
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_084
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_084 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_084',
    'nickname': 'Kakushadze Alpha #84',
    'theme': ['momentum'],
    'formula_latex': 'SignedPower(Ts_Rank(vwap-ts_max(vwap,15), 21), delta(close,5))',
    'columns_required': ['close', 'vwap'],
    'extras_required': [],
    'requires_sector': False,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 35,
    'notes': "SignedPower with a delta(close,5) exponent can produce non-finite values when the exponent is large; non-finite outputs are clipped to NaN to satisfy the registry's no-inf invariant.",
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_084 import (
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
