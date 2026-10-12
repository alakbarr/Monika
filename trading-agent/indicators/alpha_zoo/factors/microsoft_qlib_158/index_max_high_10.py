# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/index_max_high_10.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_high_10
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_high_10
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_high_10 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_imax10',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_argmax}(\\\\mathrm{high}, 10) / 10',
    'columns_required': ['high'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 10,
    'min_warmup_bars': 10,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.index_max_high_10 import (
    annotations,
    compute,
    ts_argmax,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "ts_argmax",
]
