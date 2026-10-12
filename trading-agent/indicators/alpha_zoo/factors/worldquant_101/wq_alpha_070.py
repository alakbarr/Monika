# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_070.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_070
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_070
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_070 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_070',
    'nickname': 'Kakushadze Alpha #70',
    'theme': ['momentum', 'volume'],
    'formula_latex': '(rank(delta(vwap,1))^Ts_Rank(correlation(IndNeutralize(close,industry), adv50, 18), 18)) * -1',
    'columns_required': ['close', 'volume', 'vwap'],
    'extras_required': [],
    'requires_sector': True,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 84,
    'notes': "Industry neutralization implemented via per-row sector group demean (panel['sector'] required). When sector tag is absent the registry rejects via SkipAlpha; the compute() also has a degraded global demean fallback. This is a partial approximation of the paper's IndClass.industry/subindustry/sector neutralization.",
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_070 import (
    ALPHA_ID,
    _ind_neutralize,
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
    "_ind_neutralize",
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
