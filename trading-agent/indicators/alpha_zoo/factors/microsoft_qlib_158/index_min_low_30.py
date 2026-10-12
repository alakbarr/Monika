# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/index_min_low_30.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_30
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_30
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_30 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_imin30',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_argmin}(\\\\mathrm{low}, 30) / 30',
    'columns_required': ['low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 30,
    'min_warmup_bars': 30,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_min_low_30 import (
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
