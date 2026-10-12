# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_100.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_100
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_100
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_100 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_100',
    'nickname': 'Kakushadze Alpha #100',
    'theme': ['volume', 'momentum'],
    'formula_latex': '0 - 1*((1.5*scale(IN(IN(rank(((close-low)-(high-close))/(high-low)*volume), subind), subind)) - scale(IN(correlation(close, rank(adv20), 5) - rank(ts_argmin(close,30)), subind))) * (volume/adv20))',
    'columns_required': ['high', 'low', 'close', 'volume'],
    'extras_required': [],
    'requires_sector': True,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 30,
    'notes': "Industry neutralization implemented via per-row sector group demean (panel['sector'] required). When sector tag is absent the registry rejects via SkipAlpha; the compute() also has a degraded global demean fallback. This is a partial approximation of the paper's IndClass.industry/subindustry/sector neutralization.",
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_100 import (
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
