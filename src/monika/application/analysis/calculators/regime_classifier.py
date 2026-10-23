"""Compatibility shim: Technical regime classifier.

Canonical implementation has been consolidated to:
monika.application.analysis.calculators.technical_regime_calculator
"""

from __future__ import annotations

from monika.application.analysis.calculators.technical_regime_calculator import (
    _get_atr_series,
    _get_latest_adx,
    classify_market_regime,
    compute_bollinger_donchian_chop,
)

__all__ = [
    "_get_atr_series",
    "_get_latest_adx",
    "classify_market_regime",
    "compute_bollinger_donchian_chop",
]
