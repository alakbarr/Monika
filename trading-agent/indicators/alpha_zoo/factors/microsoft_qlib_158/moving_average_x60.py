# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/moving_average_x60.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.moving_average_x60
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.moving_average_x60
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.moving_average_x60 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_max60',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_max}(\\\\mathrm{high}, 60) / \\\\mathrm{close}',
    'columns_required': ['high', 'close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.moving_average_x60 import (
    annotations,
    compute,
    safe_div,
    ts_max,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "safe_div",
    "ts_max",
]
