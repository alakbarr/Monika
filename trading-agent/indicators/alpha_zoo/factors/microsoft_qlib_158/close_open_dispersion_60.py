# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/close_open_dispersion_60.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.close_open_dispersion_60
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.close_open_dispersion_60
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.close_open_dispersion_60 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_cord60',
    'theme': ['volume', 'microstructure'],
    'formula_latex': '\\\\mathrm{ts\\\\_corr}(\\\\mathrm{close}/\\\\mathrm{close}_{{-1}}, \\\\log((\\\\mathrm{volume}+1)/(\\\\mathrm{volume}_{{-1}}+1)), 60)',
    'columns_required': ['close', 'volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.close_open_dispersion_60 import (
    annotations,
    compute,
    safe_div,
    ts_corr,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "safe_div",
    "ts_corr",
]
