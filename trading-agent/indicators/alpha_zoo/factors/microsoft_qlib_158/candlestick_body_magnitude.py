# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/candlestick_body_magnitude.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_magnitude
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_magnitude
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_magnitude as _canonical

__alpha_meta__ = {
    'id': 'qlib158_kmid',
    'theme': ['microstructure'],
    'formula_latex': '(\\\\mathrm{close} - \\\\mathrm{open}) / \\\\mathrm{open}',
    'columns_required': ['open', 'close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 1,
    'min_warmup_bars': 1,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_body_magnitude import (
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
