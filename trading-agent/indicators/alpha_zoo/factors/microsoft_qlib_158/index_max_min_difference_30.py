# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/index_max_min_difference_30.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_30
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_30
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_30 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_imxd30',
    'theme': ['momentum'],
    'formula_latex': '(\\\\mathrm{ts\\\\_argmax}(\\\\mathrm{high}, 30) - \\\\mathrm{ts\\\\_argmin}(\\\\mathrm{low}, 30)) / 30',
    'columns_required': ['high', 'low'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 30,
    'min_warmup_bars': 30,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_min_difference_30 import (
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
