# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/amihud_illiquidity.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.amihud_illiquidity
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.amihud_illiquidity
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.amihud_illiquidity as _canonical

__alpha_meta__ = {
    'id': 'academic_illiq',
    'nickname': 'Amihud 2002 illiquidity — |return| per dollar volume',
    'theme': ['liquidity'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(\mathrm{ts\_mean}(|r_t| / (\mathrm{close}_t \cdot \mathrm{volume}_t),\,21)\bigr)',
    'columns_required': ['close', 'volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 21,
    'min_warmup_bars': 22,
    'notes': (
        'Amihud (2002) ILLIQ. Daily |simple return| divided by dollar volume '
        '(close * volume), averaged over a trailing 21-day window, then '
        'cross-sectional z-score per date for long-short ranking. Top z-scores = '
        'least liquid names, which carry the illiquidity premium. Uses a 1-day '
        'return (one extra warmup bar over the 21-day average window).'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.amihud_illiquidity import (
    _cross_sectional_zscore,
    annotations,
    compute,
    safe_div,
    ts_mean,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "safe_div",
    "ts_mean",
]
