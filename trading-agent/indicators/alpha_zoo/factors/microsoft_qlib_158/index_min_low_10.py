# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/index_min_low_10.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_10
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_10
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_10 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_imin10',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_argmin}(\\\\mathrm{low}, 10) / 10',
    'columns_required': ['low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 10,
    'min_warmup_bars': 10,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_10 import (
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
