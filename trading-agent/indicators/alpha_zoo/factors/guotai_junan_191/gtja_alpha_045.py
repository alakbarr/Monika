# ==============================================================================
# File: indicators/alpha_zoo/factors/guotai_junan_191/gtja_alpha_045.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_045
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_045
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_045 as _canonical

__alpha_meta__ = {
    "id": "gtja191_045",
    "theme": ['volume'],
    "formula_latex": '(RANK(DELTA((((CLOSE*0.6)+(OPEN*0.4))),1)) * RANK(CORR(VWAP,MEAN(VOLUME,150),15)))',
    "columns_required": ['close', 'open', 'volume', 'amount'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 15,
    "min_warmup_bars": 44,
    "notes": '150d MA volume approximated with 30d window.',
}

from monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_045 import (
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
