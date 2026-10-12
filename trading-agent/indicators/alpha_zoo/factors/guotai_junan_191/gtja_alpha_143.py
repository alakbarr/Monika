# ==============================================================================
# File: indicators/alpha_zoo/factors/guotai_junan_191/gtja_alpha_143.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_143
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_143
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_143 as _canonical

__alpha_meta__ = {
    'id': 'gtja191_143',
    'theme': ['momentum'],
    'formula_latex': 'cumprod(1 + (c/delay(c,1)-1) if c>delay(c,1) else 0)',
    'columns_required': ['close'],
    'extras_required': [],
    'universe': ['equity_cn'],
    'frequency': ['1d'],
    'decay_horizon': 1,
    'min_warmup_bars': 2,
    'notes': 'Recursive SELF unrolled to cumulative product of (1 + up_return) since series start.',
}

from monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_143 import (
    ALPHA_ID,
    annotations,
    compute,
    decay_linear,
    delta,
    rank,
    safe_div,
    scale,
    signed_power,
    ts_argmax,
    ts_argmin,
    ts_corr,
    ts_cov,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ALPHA_ID",
    "annotations",
    "compute",
    "decay_linear",
    "delta",
    "rank",
    "safe_div",
    "scale",
    "signed_power",
    "ts_argmax",
    "ts_argmin",
    "ts_corr",
    "ts_cov",
    "ts_max",
    "ts_mean",
    "ts_min",
    "ts_rank",
    "ts_std",
]
