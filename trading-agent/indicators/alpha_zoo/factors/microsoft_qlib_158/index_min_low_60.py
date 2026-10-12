# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/index_min_low_60.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_60
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_60
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_60 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_imin60',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_argmin}(\\\\mathrm{low}, 60) / 60',
    'columns_required': ['low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_60 import (
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
