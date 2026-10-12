# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/candlestick_length.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_length
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_length
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_length as _canonical

__alpha_meta__ = {
    'id': 'qlib158_klen',
    'theme': ['microstructure'],
    'formula_latex': '(\\\\mathrm{high} - \\\\mathrm{low}) / \\\\mathrm{open}',
    'columns_required': ['open', 'high', 'low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 1,
    'min_warmup_bars': 1,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_length import (
    annotations,
    compute,
    safe_div,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "safe_div",
]
