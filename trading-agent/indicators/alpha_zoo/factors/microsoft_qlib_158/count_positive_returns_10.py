# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/count_positive_returns_10.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_positive_returns_10
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_positive_returns_10
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_positive_returns_10 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_cntp10',
    'theme': ['reversal'],
    'formula_latex': '\\\\mathrm{rolling\\\\_mean}(\\\\mathrm{1}[\\\\mathrm{close}>\\\\mathrm{close}_{{-1}}], 10)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 10,
    'min_warmup_bars': 10,
    'notes': 'A missing close leaves window+1 rolling rows NaN; on sparse panels this can trigger the >95% NaN registry guard (from ~30% missing bars).',
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_positive_returns_10 import (
    annotations,
    compute,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
]
