# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models"""

import sys
import monika.infrastructure.database.domain_models as _canonical
from monika.infrastructure.database.domain_models import (
    Base,
    _utcnow,
    PriceOHLCV,
    OrderBlock,
    Position,
    TradeOutcome,
    DecisionReflection,
    FundamentalBrief,
    AssetAnalysis,
    TradingEvent,
    SystemConfig,
    NewsItem,
    EconomicCalendar,
)

__all__ = [
    "Base",
    "_utcnow",
    "PriceOHLCV",
    "OrderBlock",
    "Position",
    "TradeOutcome",
    "DecisionReflection",
    "FundamentalBrief",
    "AssetAnalysis",
    "TradingEvent",
    "SystemConfig",
    "NewsItem",
    "EconomicCalendar",
]

