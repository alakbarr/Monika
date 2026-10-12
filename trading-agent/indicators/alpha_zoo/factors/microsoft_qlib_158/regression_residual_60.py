# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/regression_residual_60.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_60
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_60
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_60 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_resi60',
    'theme': ['momentum'],
    'formula_latex': '(\\\\mathrm{close} - \\\\mathrm{ts\\\\_mean}(\\\\mathrm{close}, 60)) / \\\\mathrm{close}',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_60 import (
    annotations,
    compute,
    safe_div,
    ts_mean,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "safe_div",
    "ts_mean",
]
