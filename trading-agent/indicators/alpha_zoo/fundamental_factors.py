# ==============================================================================
# File: indicators/alpha_zoo/fundamental_factors.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.fundamental_factors
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.fundamental_factors
"""

import sys
import monika.domain.indicators.alpha_zoo.fundamental_factors as _canonical

from monika.domain.indicators.alpha_zoo.fundamental_factors import (
    AlphaMeta,
    FactorRegistry,
    annotations,
    fundamental_asset_growth,
    fundamental_earnings_yield,
    safe_div,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaMeta",
    "FactorRegistry",
    "annotations",
    "fundamental_asset_growth",
    "fundamental_earnings_yield",
    "safe_div",
]
