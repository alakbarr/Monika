# ==============================================================================
# File: indicators/alpha_zoo/factors/guotai_junan_191/gtja_alpha_075.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_075
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_075
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_075 as _canonical

__alpha_meta__ = {
    "id": "gtja191_075",
    "theme": ['sentiment', 'momentum'],
    "formula_latex": 'COUNT((CLOSE>OPEN & BENCHMARKINDEXCLOSE<DELAY(BENCHMARKINDEXCLOSE,1)),50)/COUNT(BENCHMARKINDEXCLOSE<DELAY(BENCHMARKINDEXCLOSE,1),50)',
    "columns_required": ['close', 'open'],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1d"],
    "decay_horizon": 50,
    "min_warmup_bars": 30,
    "notes": 'Benchmark unavailable in zoo panel; degraded to row-mean(close) as benchmark proxy. Window 50→20. See notes.',
}

from monika.domain.indicators.alpha_zoo.factors.guotai_junan_191.gtja_alpha_075 import (
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
