# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/wq_alpha_056.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_056
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_056
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_056 as _canonical

__alpha_meta__ = {
    'id': 'alpha101_056',
    'nickname': 'Kakushadze Alpha #56',
    'theme': ['momentum'],
    'formula_latex': '0 - 1*(rank(sum(returns,10)/sum(sum(returns,2),3)) * rank((returns * cap)))  [cap unavailable -> 1]',
    'columns_required': ['close'],
    'extras_required': [],
    'requires_sector': True,
    'universe': ['equity_us', 'equity_in', 'equity_kr'],
    'frequency': ['1D'],
    'decay_horizon': 5,
    'min_warmup_bars': 10,
    'notes': "Industry neutralization implemented via per-row sector group demean (panel['sector'] required). When sector tag is absent the registry rejects via SkipAlpha; the compute() also has a degraded global demean fallback. This is a partial approximation of the paper's IndClass.industry/subindustry/sector neutralization. Paper formula uses market 'cap' which is not part of the standard OHLCV panel; substituted by a constant 1.0 DataFrame. Result remains a valid factor but loses the cap-weighting term.",
}

from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_056 import (
    ALPHA_ID,
    _make_one,
    _rolling_sum,
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
    "_make_one",
    "_rolling_sum",
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
