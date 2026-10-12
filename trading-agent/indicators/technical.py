# ==============================================================================
# File: indicators/technical.py
# Description: Backward-compatibility shim for monika.domain.indicators.technical
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.technical
"""

import sys
import monika.domain.indicators.technical as _canonical

from monika.domain.indicators.technical import (
    PriceOHLCV,
    TechnicalIndicator,
    TechnicalIndicatorCalculator,
    _WARNED_INSUFFICIENT_BARS,
    compute_ichimoku,
    compute_lag1_autocorrelation,
    compute_pivot_points,
    compute_yang_zhang_volatility,
    detect_macd_divergence,
    detect_rsi_divergence,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "PriceOHLCV",
    "TechnicalIndicator",
    "TechnicalIndicatorCalculator",
    "_WARNED_INSUFFICIENT_BARS",
    "compute_ichimoku",
    "compute_lag1_autocorrelation",
    "compute_pivot_points",
    "compute_yang_zhang_volatility",
    "detect_macd_divergence",
    "detect_rsi_divergence",
    "logger",
]
