# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/count_down_ratio_20.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_down_ratio_20
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_down_ratio_20
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_down_ratio_20 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_cntd20',
    'theme': ['reversal'],
    'formula_latex': '\\\\mathrm{CNTP}_20 - \\\\mathrm{CNTN}_20',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 20,
    'min_warmup_bars': 20,
    'notes': 'A missing close leaves window+1 rolling rows NaN; on sparse panels this can trigger the >95% NaN registry guard (from ~15% missing bars).',
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_down_ratio_20 import (
    annotations,
    compute,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
]
