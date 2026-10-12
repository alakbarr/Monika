# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/robust_minus_weak_profitability.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.robust_minus_weak_profitability
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.robust_minus_weak_profitability
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.robust_minus_weak_profitability as _canonical

__alpha_meta__ = {
    'id': 'academic_rmw',
    'nickname': '[PRICE PROXY] FF2015 RMW — quality via inverse 60d volatility',
    'theme': ['quality'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(-\mathrm{ts\_std}((\mathrm{close}_t - \mathrm{close}_{t-1}) / \mathrm{close}_{t-1},\,60)\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
    'notes': (
        '[PRICE PROXY] for the Fama-French (2015) RMW (Robust Minus Weak) '
        'profitability factor. The original definition uses operating profitability '
        'from fundamental data; here we use the negative of 60-day return volatility '
        'as a low-vol-quality proxy, then cross-sectional z-score per date for '
        'long-short ranking. Top z-scores = lower vol (quality / robust).'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.robust_minus_weak_profitability import (
    _cross_sectional_zscore,
    annotations,
    compute,
    delta,
    safe_div,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "delta",
    "safe_div",
    "ts_std",
]
