# ==============================================================================
# File: indicators/alpha_zoo/factors/guotai_junan_191/gtja_alpha_030.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_030
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_030
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_030 as _canonical

__alpha_meta__ = {
    "id": "gtja191_030",
    "theme": ['volatility'],
    "formula_latex": 'WMA((REGRESI(CLOSE/DELAY(CLOSE,1)-1, MKT_RET, SMB, HML, 60))^2, 20)',
    "columns_required": ['close'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 20,
    "min_warmup_bars": 21,
    "notes": 'Multi-factor REGRESI not implementable in pure-fn zoo; degraded to WMA of squared daily return (idio proxy). See notes.',
}

from monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_030 import (
    annotations,
    compute,
    decay_linear,
    delta,
    rank,
    safe_div,
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
    "annotations",
    "compute",
    "decay_linear",
    "delta",
    "rank",
    "safe_div",
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
