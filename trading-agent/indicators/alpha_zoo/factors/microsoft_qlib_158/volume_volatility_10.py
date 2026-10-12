# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/volume_volatility_10.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_volatility_10
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_volatility_10
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_volatility_10 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_vstd10',
    'theme': ['volume', 'volatility'],
    'formula_latex': '\\\\mathrm{ts\\\\_std}(\\\\mathrm{volume}, 10) / \\\\mathrm{volume}',
    'columns_required': ['volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 10,
    'min_warmup_bars': 10,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.volume_volatility_10 import (
    annotations,
    compute,
    safe_div,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "safe_div",
    "ts_std",
]
