# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/candlestick_body_shift.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_shift
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_shift
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_shift as _canonical

__alpha_meta__ = {
    'id': 'qlib158_ksft',
    'theme': ['microstructure'],
    'formula_latex': '(2\\\\,\\\\mathrm{close} - \\\\mathrm{high} - \\\\mathrm{low}) / \\\\mathrm{open}',
    'columns_required': ['open', 'high', 'low', 'close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 1,
    'min_warmup_bars': 1,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_shift import (
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
