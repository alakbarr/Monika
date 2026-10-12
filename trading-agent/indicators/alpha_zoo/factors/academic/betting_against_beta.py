# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/betting_against_beta.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.betting_against_beta
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.betting_against_beta
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.betting_against_beta as _canonical

__alpha_meta__ = {
    'id': 'academic_bab',
    'nickname': 'Frazzini-Pedersen 2014 betting-against-beta',
    'theme': ['volatility'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(-\,\mathrm{ts\_cov}(r_i, r_m, 252) / \mathrm{ts\_std}(r_m, 252)^2\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 252,
    'min_warmup_bars': 253,
    'notes': (
        'Frazzini & Pedersen (2014) BAB. Price-only proxy: market return is the '
        'cross-sectional mean of daily per-stock returns (equal-weighted, not '
        'value-weighted as in the original). Beta is Cov(r_i, r_m) / Var(r_m) '
        'over a single 252-day window (paper uses separate 1y vol / 5y '
        'correlation windows). Factor score is negative beta, cross-sectional '
        'z-scored so low-beta names rank highest, matching the long leg of the '
        'original long-short construction.'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.betting_against_beta import (
    _cross_sectional_zscore,
    annotations,
    compute,
    ts_cov,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "ts_cov",
    "ts_std",
]
