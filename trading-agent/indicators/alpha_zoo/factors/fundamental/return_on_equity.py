# ==============================================================================
# File: indicators/alpha_zoo/factors/fundamental/return_on_equity.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.fundamental.return_on_equity
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.fundamental.return_on_equity
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.fundamental.return_on_equity as _canonical

__alpha_meta__ = {
    "id": "fund_roe",
    "nickname": "ROE - return on equity (PIT-safe fundamentals)",
    "theme": ["quality"],
    "formula_latex": r"\mathrm{zscore}_{x}(\mathrm{ROE})",
    "columns_required": ["fund:roe"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "PIT-safe return on equity from the fundamental panel; cross-sectional "
        "z-score per date. Missing statements remain NaN and are excluded from "
        "that date's cross-section."
    ),
}

from monika.domain.indicators.alpha_zoo.factors.fundamental.return_on_equity import (
    annotations,
    compute,
    zscore,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "zscore",
]
