# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/count_negative_returns_30.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_negative_returns_30
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_negative_returns_30
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_negative_returns_30 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_cntn30',
    'theme': ['reversal'],
    'formula_latex': '\\\\mathrm{rolling\\\\_mean}(\\\\mathrm{1}[\\\\mathrm{close}<\\\\mathrm{close}_{{-1}}], 30)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 30,
    'min_warmup_bars': 30,
    'notes': 'A missing close leaves window+1 rolling rows NaN; on sparse panels this can trigger the >95% NaN registry guard (from ~10% missing bars).',
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.count_negative_returns_30 import (
    annotations,
    compute,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
]
