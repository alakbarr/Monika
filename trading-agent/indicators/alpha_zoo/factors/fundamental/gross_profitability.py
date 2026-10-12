# ==============================================================================
# File: indicators/alpha_zoo/factors/fundamental/gross_profitability.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.fundamental.gross_profitability
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.fundamental.gross_profitability
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.fundamental.gross_profitability as _canonical

__alpha_meta__ = {
    "id": "fund_gross_profitability",
    "nickname": "Gross profitability - gross profit over total assets",
    "theme": ["quality"],
    "formula_latex": r"\mathrm{zscore}_{x}(\mathrm{gross\_profit}/\mathrm{total\_assets})",
    "columns_required": ["fund:gross_profitability"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "PIT-safe Novy-Marx style gross profitability from the fundamental "
        "panel; cross-sectional z-score per date with missing issuers excluded."
    ),
}

from monika.domain.indicators.alpha_zoo.factors.fundamental.gross_profitability import (
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
