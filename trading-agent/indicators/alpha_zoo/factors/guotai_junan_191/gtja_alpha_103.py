# ==============================================================================
# File: indicators/alpha_zoo/factors/guotai_junan_191/gtja_alpha_103.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_103
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_103
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_103 as _canonical

__alpha_meta__ = {
    'id': 'gtja191_103',
    'theme': ['reversal'],
    'formula_latex': '((20-lowday(low,20))/20)*100',
    'columns_required': ['close', 'low'],
    'extras_required': [],
    'universe': ['equity_cn'],
    'frequency': ['1d'],
    'decay_horizon': 20,
    'min_warmup_bars': 20,
    'notes': 'Days since the most recent extreme; today=0. Ties choose the latest bar (port policy).',
}

from monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_103 import (
    ALPHA_ID,
    annotations,
    compute,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ALPHA_ID",
    "annotations",
    "compute",
]
