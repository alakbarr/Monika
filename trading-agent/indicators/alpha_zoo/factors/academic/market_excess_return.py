# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/market_excess_return.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.market_excess_return
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.market_excess_return
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.market_excess_return as _canonical

__alpha_meta__ = {
    'id': 'academic_mkt_rf',
    'nickname': '[PRICE PROXY] Market factor (Sharpe 1964) — 21d demeaned return',
    'theme': ['momentum'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl((\mathrm{close}_t - \mathrm{close}_{t-21}) / \mathrm{close}_{t-21}\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 21,
    'min_warmup_bars': 21,
    'notes': (
        '[PRICE PROXY] for the Sharpe (1964) / Fama-French market factor (MKT-RF). '
        'The original definition uses value-weighted market excess returns; here we '
        'use a 21-day per-stock total return and cross-sectional z-score per date '
        'for long-short ranking. Top z-scores = strong recent winners; bottom = losers.'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.market_excess_return import (
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
