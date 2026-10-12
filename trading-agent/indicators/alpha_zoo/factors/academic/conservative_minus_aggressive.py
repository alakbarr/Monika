# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/conservative_minus_aggressive.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.conservative_minus_aggressive
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.conservative_minus_aggressive
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.conservative_minus_aggressive as _canonical

__alpha_meta__ = {
    'id': 'academic_cma',
    'nickname': '[PRICE PROXY] FF2015 CMA — investment via inverse volume growth',
    'theme': ['quality'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(-\Delta_{60}\log(\mathrm{ts\_mean}(\mathrm{volume},\,60) + 1)\bigr)',
    'columns_required': ['volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 120,
    'notes': (
        '[PRICE PROXY] for the Fama-French (2015) CMA (Conservative Minus '
        'Aggressive) investment factor. The original definition uses total-asset '
        'growth from fundamental data; here we use the negative 60-day change in '
        'log average volume as an activity-growth proxy, then cross-sectional '
        'z-score per date for long-short ranking. Top z-scores = volume contraction '
        '(conservative / low-growth proxy).'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.conservative_minus_aggressive import (
    _cross_sectional_zscore,
    annotations,
    compute,
    delta,
    ts_mean,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "delta",
    "ts_mean",
]
