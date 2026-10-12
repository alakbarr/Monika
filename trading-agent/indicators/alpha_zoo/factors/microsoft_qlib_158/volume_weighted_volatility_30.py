# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/volume_weighted_volatility_30.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_30
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_30
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_30 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_wvma30',
    'theme': ['volume', 'volatility'],
    'formula_latex': '\\\\mathrm{ts\\\\_std}(|\\\\mathrm{ret}|\\\\cdot v, 30) / \\\\mathrm{ts\\\\_mean}(|\\\\mathrm{ret}|\\\\cdot v, 30)',
    'columns_required': ['close', 'volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 30,
    'min_warmup_bars': 30,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_30 import (
    annotations,
    compute,
    safe_div,
    ts_mean,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "safe_div",
    "ts_mean",
    "ts_std",
]
