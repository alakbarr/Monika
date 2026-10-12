# ==============================================================================
# File: indicators/alpha_zoo/factors/guotai_junan_191/gtja_alpha_174.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_174
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_174
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_174 as _canonical

__alpha_meta__ = {
    'id': 'gtja191_174',
    'theme': ['volatility'],
    'formula_latex': 'sma((c>delay(c,1)?std(c,20):0),20,1)',
    'columns_required': ['close'],
    'extras_required': [],
    'universe': ['equity_cn'],
    'frequency': ['1d'],
    'decay_horizon': 20,
    'min_warmup_bars': 22,
    'notes': '',
}

from monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_174 import (
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
