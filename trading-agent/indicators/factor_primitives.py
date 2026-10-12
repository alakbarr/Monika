# ==============================================================================
# File: indicators/factor_primitives.py
# Description: Backward-compatibility shim for monika.domain.indicators.factor_primitives
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.factor_primitives
"""

import sys
import monika.domain.indicators.factor_primitives as _canonical

from monika.domain.indicators.factor_primitives import (
    HAS_BOTTLENECK,
    Market,
    _as_float,
    annotations,
    decay_linear,
    delta,
    logger,
    observed_over,
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
    vwap,
    zscore,
)

sys.modules[__name__] = _canonical

__all__ = [
    "HAS_BOTTLENECK",
    "Market",
    "_as_float",
    "annotations",
    "decay_linear",
    "delta",
    "logger",
    "observed_over",
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
    "vwap",
    "zscore",
]
