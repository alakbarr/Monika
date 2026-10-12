# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/regression_r_squared_60.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_60
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_60
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_60 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_rsqr60',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_corr}(\\\\mathrm{close}, t, 60)^2',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_r_squared_60 import (
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
