# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_097.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_097
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_097
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_097 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_097',
    'nickname': 'Kakushadze Alpha #97',
    'theme': ['volume'],
    'formula_latex': '(rank(decay_linear(delta(IndNeutralize(0.721*low+0.279*vwap, industry),3),20)) - Ts_Rank(decay_linear(Ts_Rank(correlation(Ts_Rank(low,8), Ts_Rank(adv60,17), 5), 19), 16),16)) * -1',
    'columns_required': ['low', 'volume', 'vwap', 'close'],
    'extras_required': [],
    'requires_sector': True,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 128,
    'notes': "Industry neutralization implemented via per-row sector group demean (panel['sector'] required). When sector tag is absent the registry rejects via SkipAlpha; the compute() also has a degraded global demean fallback. This is a partial approximation of the paper's IndClass.industry/subindustry/sector neutralization.",
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_097 import (
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
