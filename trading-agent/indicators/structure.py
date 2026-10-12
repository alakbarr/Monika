# ==============================================================================
# File: indicators/structure.py
# Description: Backward-compatibility shim for monika.domain.indicators.structure
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.structure
"""

import sys
import monika.domain.indicators.structure as _canonical

from monika.domain.indicators.structure import (
    FVGData,
    FVGZone,
    FVG_MAX_DISTANCE,
    LiquidityZone,
    LiquidityZoneData,
    MarketStructureAnalyzer,
    OrderBlock,
    OrderBlockData,
    PriceOHLCV,
    SRZone,
    StructureBreak,
    StructureBreakData,
    SwingPoint,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FVGData",
    "FVGZone",
    "FVG_MAX_DISTANCE",
    "LiquidityZone",
    "LiquidityZoneData",
    "MarketStructureAnalyzer",
    "OrderBlock",
    "OrderBlockData",
    "PriceOHLCV",
    "SRZone",
    "StructureBreak",
    "StructureBreakData",
    "SwingPoint",
    "logger",
]
