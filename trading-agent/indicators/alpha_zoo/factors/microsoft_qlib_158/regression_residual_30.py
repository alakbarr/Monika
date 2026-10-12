# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/regression_residual_30.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_30
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_30
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_30 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_resi30',
    'theme': ['momentum'],
    'formula_latex': '(\\\\mathrm{close} - \\\\mathrm{ts\\\\_mean}(\\\\mathrm{close}, 30)) / \\\\mathrm{close}',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 30,
    'min_warmup_bars': 30,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.regression_residual_30 import (
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
