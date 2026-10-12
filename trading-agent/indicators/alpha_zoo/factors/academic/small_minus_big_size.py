# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/small_minus_big_size.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.small_minus_big_size
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.small_minus_big_size
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.small_minus_big_size as _canonical

__alpha_meta__ = {
    'id': 'academic_smb',
    'nickname': '[PRICE PROXY] FF1993 SMB — small-minus-big via inverse dollar-volume',
    'theme': ['quality'],
    'formula_latex': r'\mathrm{zscore}_{x}\bigl(-\log(\mathrm{ts\_mean}(\mathrm{volume} \cdot \mathrm{close},\,60) + 1)\bigr)',
    'columns_required': ['close', 'volume'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk'],
    'frequency': ['1d'],
    'decay_horizon': 60,
    'min_warmup_bars': 60,
    'notes': (
        '[PRICE PROXY] for the Fama-French (1993) SMB (Small Minus Big) size factor. '
        'The original definition uses market capitalization from book equity data; here '
        'we use the negative log of 60-day average dollar volume (close * volume) as a '
        'liquidity-weighted size proxy, then cross-sectional z-score per date for '
        'long-short ranking. Top z-scores = smaller / less liquid names.'
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.small_minus_big_size import (
    _cross_sectional_zscore,
    annotations,
    compute,
    ts_mean,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "annotations",
    "compute",
    "ts_mean",
]
