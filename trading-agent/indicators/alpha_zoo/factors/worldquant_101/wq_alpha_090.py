# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_090.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_090
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_090
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_090 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_090',
    'nickname': 'Kakushadze Alpha #90',
    'theme': ['volume'],
    'formula_latex': '(rank(close-ts_max(close,5))^Ts_Rank(correlation(IndNeutralize(adv40, subindustry), low, 5), 3)) * -1',
    'columns_required': ['low', 'close', 'volume'],
    'extras_required': [],
    'requires_sector': True,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 46,
    'notes': "Industry neutralization implemented via per-row sector group demean (panel['sector'] required). When sector tag is absent the registry rejects via SkipAlpha; the compute() also has a degraded global demean fallback. This is a partial approximation of the paper's IndClass.industry/subindustry/sector neutralization.",
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_090 import (
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
