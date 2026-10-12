# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/correlation_rewiring.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic.correlation_rewiring
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic.correlation_rewiring
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic.correlation_rewiring as _canonical

__alpha_meta__ = {
    "id": "academic_corr_rewire",
    "nickname": "correlation-rewiring stability score",
    "theme": ["volatility"],
    "formula_latex": (
        r"\mathrm{zscore}_{x}\Bigl(-\,\frac{1}{|J_i|}\sum_{j \in J_i}"
        r"\bigl|\rho_{ij}^{\mathrm{event}} - \rho_{ij}^{\mathrm{calm}}\bigr|\Bigr),"
        r"\quad \rho^{\mathrm{event}} = \mathrm{corr}(r_{t-19..t}),\ "
        r"\rho^{\mathrm{calm}} = \mathrm{corr}(r_{t-139..t-20})"
    ),
    "columns_required": ["close"],
    "universe": ["equity_us", "equity_cn", "equity_hk", "crypto"],
    "frequency": ["1d"],
    "decay_horizon": 60,
    "min_warmup_bars": 142,
    "notes": (
        "Causal rolling rendition of the correlation-regime skill's Mode 4 "
        "(rewiring leaderboard): per-asset row mean of |corr(event) - "
        "corr(calm)| where the event window is the trailing 20 bars and the "
        "calm baseline is the 120 bars immediately before it, sign-flipped "
        "and cross-sectionally z-scored so correlation-stable names rank "
        "highest. Framed as a structural risk / crowding lens, not a "
        "validated alpha: the author's public validation of the underlying "
        "regime machinery covers regime detection and attribution on "
        "historical replays only and makes no return-prediction claim for "
        "this cross-sectional form. Missing data: columns need >= 90% "
        "in-window coverage, else NaN; observed entries are demeaned and "
        "missing entries contribute zero to the correlation cross-products."
    ),
}

from monika.domain.indicators.alpha_zoo.factors.academic.correlation_rewiring import (
    _cross_sectional_zscore,
    _rewiring_scores,
    _window_corr,
    annotations,
    compute,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_cross_sectional_zscore",
    "_rewiring_scores",
    "_window_corr",
    "annotations",
    "compute",
]
