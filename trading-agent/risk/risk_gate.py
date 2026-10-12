# ==============================================================================
# File: risk/risk_gate.py
# Description: Backward-compatibility shim for monika.domain.risk.risk_gate
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.risk_gate
"""

import sys
import monika.domain.risk.risk_gate as _canonical

from monika.domain.risk.risk_gate import (
    AssetAnalysis,
    EconomicCalendar,
    Order,
    OrderLog,
    OrderStatus,
    PaperTradeRecord,
    Position,
    RiskGate,
    RiskState,
    RiskVerdict,
    SYMBOL_CURRENCIES,
    SizingResult,
    SystemConfig,
    TradeOutcome,
    get_current_risk_state,
    get_daily_risk_cutoff,
    get_symbol_currencies,
    get_trading_day_start,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AssetAnalysis",
    "EconomicCalendar",
    "Order",
    "OrderLog",
    "OrderStatus",
    "PaperTradeRecord",
    "Position",
    "RiskGate",
    "RiskState",
    "RiskVerdict",
    "SYMBOL_CURRENCIES",
    "SizingResult",
    "SystemConfig",
    "TradeOutcome",
    "get_current_risk_state",
    "get_daily_risk_cutoff",
    "get_symbol_currencies",
    "get_trading_day_start",
    "logger",
]
