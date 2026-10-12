# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/candlestick_upper_shadow.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_upper_shadow
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_upper_shadow
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_upper_shadow as _canonical

__alpha_meta__ = {
    'id': 'qlib158_kup',
    'theme': ['microstructure'],
    'formula_latex': '(\\\\mathrm{high} - \\\\max(\\\\mathrm{open}, \\\\mathrm{close})) / \\\\mathrm{open}',
    'columns_required': ['open', 'high', 'close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 1,
    'min_warmup_bars': 1,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.candlestick_upper_shadow import (
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
