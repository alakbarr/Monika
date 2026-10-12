# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models.market
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models.market"""

import sys
import monika.infrastructure.database.domain_models.market as _canonical

from monika.infrastructure.database.domain_models.market import (
    BondYieldData,
    COTReport,
    CentralBankRateExpectation,
    DXYData,
    FVGZone,
    FedWatchProbability,
    InterestRate,
    LiquidityZone,
    OrderBlock,
    PatternScreeningCache,
    PriceOHLCV,
    SRZone,
    StructureBreak,
    SwingPoint,
    TechnicalIndicator,
    TreasuryYield,
    VIXData,
)

sys.modules[__name__] = _canonical

__all__ = [
    "BondYieldData",
    "COTReport",
    "CentralBankRateExpectation",
    "DXYData",
    "FVGZone",
    "FedWatchProbability",
    "InterestRate",
    "LiquidityZone",
    "OrderBlock",
    "PatternScreeningCache",
    "PriceOHLCV",
    "SRZone",
    "StructureBreak",
    "SwingPoint",
    "TechnicalIndicator",
    "TreasuryYield",
    "VIXData",
]
