# ==============================================================================
# File: indicators/alpha_zoo/microstructure_factors.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.microstructure_factors
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.microstructure_factors
"""

import sys
import monika.domain.indicators.alpha_zoo.microstructure_factors as _canonical

from monika.domain.indicators.alpha_zoo.microstructure_factors import (
    AlphaMeta,
    FactorRegistry,
    annotations,
    delta,
    microstructure_range_dispersion,
    microstructure_shadow_asymmetry,
    microstructure_volume_price_rank_divergence,
    microstructure_volume_weighted_momentum,
    safe_div,
    signed_power,
    ts_corr,
    ts_mean,
    ts_rank,
    ts_std,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaMeta",
    "FactorRegistry",
    "annotations",
    "delta",
    "microstructure_range_dispersion",
    "microstructure_shadow_asymmetry",
    "microstructure_volume_price_rank_divergence",
    "microstructure_volume_weighted_momentum",
    "safe_div",
    "signed_power",
    "ts_corr",
    "ts_mean",
    "ts_rank",
    "ts_std",
]
