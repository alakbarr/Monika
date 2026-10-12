# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/regression_r_squared_20.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_20
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_20
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_20 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_rsqr20',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_corr}(\\\\mathrm{close}, t, 20)^2',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 20,
    'min_warmup_bars': 20,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_20 import (
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
