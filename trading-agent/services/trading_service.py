# ==============================================================================
# File: services/trading_service.py
# Description: Compatibility re-export shim for monika.application.services.trading_service
# ==============================================================================

"""
Backward-compatibility re-export shim.
Canonical implementation: monika.application.services.trading_service
"""

from monika.application.services.trading_service import (
    TradingService,
    OrderPreviewResult,
    TradeExecutionResult,
)

__all__ = [
    "TradingService",
    "OrderPreviewResult",
    "TradeExecutionResult",
]
