# ==============================================================================
# File: indicators/alpha_zoo/qlib158.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.qlib158
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.qlib158
"""

import sys
import monika.domain.indicators.alpha_zoo.qlib158 as _canonical

from monika.domain.indicators.alpha_zoo.qlib158 import (
    AlphaMeta,
    FactorRegistry,
    _calc_resi_rsqr,
    _calc_rsv,
    _calc_wvma,
    _register_resi_rsqr,
    _register_rsv,
    _register_wvma,
    annotations,
    qlib_klen,
    qlib_klow,
    qlib_kmid,
    qlib_ksft,
    qlib_kup,
    safe_div,
    ts_max,
    ts_mean,
    ts_min,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaMeta",
    "FactorRegistry",
    "_calc_resi_rsqr",
    "_calc_rsv",
    "_calc_wvma",
    "_register_resi_rsqr",
    "_register_rsv",
    "_register_wvma",
    "annotations",
    "qlib_klen",
    "qlib_klow",
    "qlib_kmid",
    "qlib_ksft",
    "qlib_kup",
    "safe_div",
    "ts_max",
    "ts_mean",
    "ts_min",
    "ts_std",
]
