# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/carhart_momentum.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.carhart_momentum
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.carhart_momentum
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.carhart_momentum as _canonical

__alpha_meta__ = {
    'id': 'academic_carhart_mom',
    'nickname': 'Carhart 1997 momentum — 12m-1m return',
    'theme': ['momentum'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl((\mathrm{close}_t - \mathrm{close}_{t-252})/\mathrm{close}_{t-252} - (\mathrm{close}_t - \mathrm{close}_{t-21})/\mathrm{close}_{t-21}\bigr)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 252,
    'notes': (
        'Carhart (1997) UMD momentum factor. 12-month return minus 1-month return, '
        'cross-sectional z-score per date for long-short ranking. Top z-scores = '
        'winners. Constructed directly from prices, so this matches the original '
        'definition modulo the z-score wrapper. Canonical 252d window; declared '
        'decay_horizon=60 due to registry schema cap (le=60); real signal horizon=252.'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.carhart_momentum import (
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
