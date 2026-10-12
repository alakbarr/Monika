# ==============================================================================
# File: indicators/alpha_zoo/alpha101.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.alpha101
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.alpha101
"""

import sys
import monika.domain.indicators.alpha_zoo.alpha101 as _canonical

from monika.domain.indicators.alpha_zoo.alpha101 import (
    AlphaMeta,
    FactorRegistry,
    annotations,
    decay_linear,
    delta,
    safe_div,
    signed_power,
    ts_argmax,
    ts_corr,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
    wq_alpha_001,
    wq_alpha_006,
    wq_alpha_012,
    wq_alpha_041,
    wq_alpha_053,
    wq_alpha_101,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaMeta",
    "FactorRegistry",
    "annotations",
    "decay_linear",
    "delta",
    "safe_div",
    "signed_power",
    "ts_argmax",
    "ts_corr",
    "ts_max",
    "ts_mean",
    "ts_min",
    "ts_rank",
    "ts_std",
    "wq_alpha_001",
    "wq_alpha_006",
    "wq_alpha_012",
    "wq_alpha_041",
    "wq_alpha_053",
    "wq_alpha_101",
]
