# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/short_term_reversal.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.short_term_reversal
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.short_term_reversal
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.short_term_reversal as _canonical

__alpha_meta__ = {
    'id': 'academic_strev',
    'nickname': 'Jegadeesh 1990 short-term reversal — inverse 21d return',
    'theme': ['reversal'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(-(\mathrm{close}_t - \mathrm{close}_{t-21}) / \mathrm{close}_{t-21}\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 21,
    'min_warmup_bars': 21,
    'notes': (
        'Jegadeesh (1990) one-month reversal. Negative trailing 21-day return, '
        'cross-sectional z-score per date for long-short ranking. Top z-scores = '
        'recent one-month losers, which tend to rebound. Constructed directly from '
        'prices, matching the original definition modulo the z-score wrapper.'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.short_term_reversal import (
    _cross_sectional_zscore,
    annotations,
    compute,
    delta,
    safe_div,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "delta",
    "safe_div",
]
