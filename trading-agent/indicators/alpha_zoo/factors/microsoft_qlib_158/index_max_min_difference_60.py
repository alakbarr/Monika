# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/index_max_min_difference_60.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_60
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_60
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_60 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_imxd60',
    'theme': ['momentum'],
    'formula_latex': '(\\\\mathrm{ts\\\\_argmax}(\\\\mathrm{high}, 60) - \\\\mathrm{ts\\\\_argmin}(\\\\mathrm{low}, 60)) / 60',
    'columns_required': ['high', 'low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_60 import (
    annotations,
    compute,
    ts_argmax,
    ts_argmin,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "ts_argmax",
    "ts_argmin",
]
