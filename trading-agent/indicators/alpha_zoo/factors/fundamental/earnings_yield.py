# ==============================================================================
# File: indicators/alpha_zoo/factors/fundamental/earnings_yield.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.fundamental.earnings_yield
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.fundamental.earnings_yield
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.fundamental.earnings_yield as _canonical

__alpha_meta__ = {
    "id": "fund_earnings_yield",
    "nickname": "Earnings yield - net income over market cap",
    "theme": ["value"],
    "formula_latex": (
        r"\mathrm{zscore}_{x}\left("
        r"\frac{\mathrm{net\_income}}{\mathrm{close}\times\mathrm{shares\_diluted}}"
        r"\right)"
    ),
    "columns_required": ["close", "fund:net_income", "fund:shares_diluted"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "Hybrid value factor using PIT-safe net income and shares diluted "
        "aligned to the daily close panel. Division by zero/non-finite market "
        "cap becomes NaN before cross-sectional scoring."
    ),
}

from monika.domain.indicators.alpha_zoo.factors.fundamental.earnings_yield import (
    annotations,
    compute,
    safe_div,
    zscore,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "safe_div",
    "zscore",
]
