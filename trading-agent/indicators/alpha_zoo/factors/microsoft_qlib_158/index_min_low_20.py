# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/index_min_low_20.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_20
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_20
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_20 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_imin20',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_argmin}(\\\\mathrm{low}, 20) / 20',
    'columns_required': ['low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 20,
    'min_warmup_bars': 20,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_20 import (
    annotations,
    compute,
    ts_argmin,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "ts_argmin",
]
