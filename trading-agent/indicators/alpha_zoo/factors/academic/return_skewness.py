# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/return_skewness.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.return_skewness
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.return_skewness
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.return_skewness as _canonical

__alpha_meta__ = {
    'id': 'academic_retskew',
    'nickname': 'Harvey-Siddique 2000 return skewness — inverse 60d skew',
    'theme': ['volatility'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(-\mathrm{skew}_{60}(r_t)\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 61,
    'notes': (
        'Harvey & Siddique (2000) skewness premium. Negative of the trailing '
        '60-day sample skewness of daily simple returns, cross-sectional z-score '
        'per date for long-short ranking. Top z-scores = most negatively-skewed '
        'names, which command a return premium over lottery-like positively-skewed '
        'names. Uses a 1-day return (one extra warmup bar over the 60-day window).'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.return_skewness import (
    _cross_sectional_zscore,
    annotations,
    compute,
    safe_div,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "safe_div",
]
