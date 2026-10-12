# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/high_minus_low_value.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.high_minus_low_value
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.high_minus_low_value
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.high_minus_low_value as _canonical

__alpha_meta__ = {
    'id': 'academic_hml',
    'nickname': '[PRICE PROXY] FF1993 HML — value via inverse 252d return',
    'theme': ['value'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(-(\mathrm{close}_t - \mathrm{close}_{t-252}) / \mathrm{close}_{t-252}\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 252,
    'notes': (
        '[PRICE PROXY] for the Fama-French (1993) HML (High Minus Low) value factor. '
        'The original definition uses book-to-market ratio from fundamental data; here '
        'we use the negative 252-day total return as a long-term reversal proxy, then '
        'cross-sectional z-score per date for long-short ranking. Top z-scores = '
        'long-term underperformers (deeper value). Canonical 252d window; declared '
        'decay_horizon=60 due to registry schema cap (le=60); real signal horizon=252.'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.high_minus_low_value import (
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
