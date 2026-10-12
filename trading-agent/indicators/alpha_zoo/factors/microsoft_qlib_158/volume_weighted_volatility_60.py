# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/volume_weighted_volatility_60.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_60
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_60
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_60 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_wvma60',
    'theme': ['volume', 'volatility'],
    'formula_latex': '\\\\mathrm{ts\\\\_std}(|\\\\mathrm{ret}|\\\\cdot v, 60) / \\\\mathrm{ts\\\\_mean}(|\\\\mathrm{ret}|\\\\cdot v, 60)',
    'columns_required': ['close', 'volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_weighted_volatility_60 import (
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
