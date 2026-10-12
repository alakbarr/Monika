# ==============================================================================
# File: indicators/alpha_zoo/factors/fundamental/asset_growth.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.fundamental.asset_growth
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.fundamental.asset_growth
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.fundamental.asset_growth as _canonical

__alpha_meta__ = {
    "id": "fund_asset_growth",
    "nickname": "Asset growth - inverse investment factor",
    "theme": ["growth"],
    "formula_latex": r"-\mathrm{zscore}_{x}(\Delta \mathrm{total\_assets}_{YoY})",
    "columns_required": ["fund:asset_growth"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "Inverse PIT-safe asset-growth factor. High asset growth is treated as "
        "aggressive investment and receives lower scores; low/negative growth "
        "receives higher scores."
    ),
}

from monika.domain.indicators.alpha_zoo.factors.fundamental.asset_growth import (
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
