# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/proximity_52_week_high.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.proximity_52_week_high
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.proximity_52_week_high
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.proximity_52_week_high as _canonical

__alpha_meta__ = {
    'id': 'academic_high52w',
    'nickname': 'George-Hwang 2004 52-week-high momentum',
    'theme': ['momentum'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(\mathrm{close}_t / \mathrm{ts\_max}(\mathrm{close},\,252)\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 252,
    'notes': (
        'George & Hwang (2004) 52-week-high momentum. Ratio of current close to the '
        'trailing 252-day maximum close, cross-sectional z-score per date for '
        'long-short ranking. Top z-scores = names trading nearest their 52-week high. '
        'Canonical 252d window; declared decay_horizon=60 due to registry schema cap '
        '(le=60); real signal horizon spans months.'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.proximity_52_week_high import (
    _cross_sectional_zscore,
    annotations,
    compute,
    safe_div,
    ts_max,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "safe_div",
    "ts_max",
]
