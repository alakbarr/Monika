# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models.trading
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models.trading"""

import sys
import monika.infrastructure.database.domain_models.trading as _canonical

from monika.infrastructure.database.domain_models.trading import (
    BacktestRun,
    BacktestTrade,
    MT5Signal,
    Order,
    OrderEvent,
    OrderLog,
    OrderStatus,
    PaperTradeRecord,
    Position,
    Trade,
    TradeOutcome,
    TradePlan,
    TradePlanLeg,
    TradeTrigger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "BacktestRun",
    "BacktestTrade",
    "MT5Signal",
    "Order",
    "OrderEvent",
    "OrderLog",
    "OrderStatus",
    "PaperTradeRecord",
    "Position",
    "Trade",
    "TradeOutcome",
    "TradePlan",
    "TradePlanLeg",
    "TradeTrigger",
]
