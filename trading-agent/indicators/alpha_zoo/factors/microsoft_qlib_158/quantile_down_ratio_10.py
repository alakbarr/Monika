# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/quantile_down_ratio_10.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.quantile_down_ratio_10
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.quantile_down_ratio_10
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.quantile_down_ratio_10 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_qtld10',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{quantile}_{{0.2}}(\\\\mathrm{close}, 10) / \\\\mathrm{close}',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 10,
    'min_warmup_bars': 10,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.quantile_down_ratio_10 import (
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
