# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/regression_r_squared_5.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_5
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_5
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_5 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_rsqr5',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_corr}(\\\\mathrm{close}, t, 5)^2',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 5,
    'min_warmup_bars': 5,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_5 import (
    annotations,
    compute,
    ts_corr,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "ts_corr",
]
