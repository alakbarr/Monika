# ==============================================================================
# File: indicators/alpha_zoo/academic_factors.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.academic_factors
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.academic_factors
"""

import sys
import monika.domain.indicators.alpha_zoo.academic_factors as _canonical

from monika.domain.indicators.alpha_zoo.academic_factors import (
    AlphaMeta,
    FactorRegistry,
    academic_amihud_illiquidity_premium,
    academic_betting_against_beta,
    academic_carhart_momentum,
    academic_idiosyncratic_volatility,
    academic_proximity_52w_high,
    annotations,
    safe_div,
    ts_mean,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaMeta",
    "FactorRegistry",
    "academic_amihud_illiquidity_premium",
    "academic_betting_against_beta",
    "academic_carhart_momentum",
    "academic_idiosyncratic_volatility",
    "academic_proximity_52w_high",
    "annotations",
    "safe_div",
    "ts_mean",
    "ts_std",
]
