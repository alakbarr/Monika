# ==============================================================================
# File: indicators/alpha_zoo/factors/guotai_junan_191/gtja_alpha_013.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_013
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_013
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_013 as _canonical

__alpha_meta__ = {
    "id": "gtja191_013",
    "theme": ['microstructure'],
    "formula_latex": '(((HIGH*LOW)^0.5) - VWAP)',
    "columns_required": ['high', 'low', 'volume', 'amount'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 1,
    "min_warmup_bars": 1,
    "notes": 'Geometric mean of high/low minus vwap.',
}

from monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_013 import (
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
