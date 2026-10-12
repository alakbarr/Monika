# ==============================================================================
# File: indicators/micro_alpha_zoo.py
# Description: Backward-compatibility shim for monika.domain.indicators.micro_alpha_zoo
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.micro_alpha_zoo
"""

import sys
import monika.domain.indicators.micro_alpha_zoo as _canonical

from monika.domain.indicators.micro_alpha_zoo import (
    FactorMetadata,
    MicroAlphaZoo,
    alpha_001,
    alpha_002,
    alpha_003,
    alpha_006,
    alpha_009,
    alpha_012,
    alpha_028,
    alpha_033,
    alpha_041,
    alpha_053,
    alpha_054,
    alpha_060,
    alpha_acceleration_momentum,
    alpha_amihud_illiquidity,
    alpha_decay_trend_strength,
    alpha_hl_volatility_ratio,
    alpha_liquidity_sweep_reversion,
    alpha_range_efficiency,
    alpha_return_skewness,
    alpha_volume_vwap_deviation,
    annotations,
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
    zscore,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FactorMetadata",
    "MicroAlphaZoo",
    "alpha_001",
    "alpha_002",
    "alpha_003",
    "alpha_006",
    "alpha_009",
    "alpha_012",
    "alpha_028",
    "alpha_033",
    "alpha_041",
    "alpha_053",
    "alpha_054",
    "alpha_060",
    "alpha_acceleration_momentum",
    "alpha_amihud_illiquidity",
    "alpha_decay_trend_strength",
    "alpha_hl_volatility_ratio",
    "alpha_liquidity_sweep_reversion",
    "alpha_range_efficiency",
    "alpha_return_skewness",
    "alpha_volume_vwap_deviation",
    "annotations",
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
    "zscore",
]
