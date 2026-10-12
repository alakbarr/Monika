# ==============================================================================
# File: execution/broker_plugin.py
# Description: Backward-compatibility shim for monika.domain.execution.broker_plugin
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.execution.broker_plugin
"""

import sys
import monika.domain.execution.broker_plugin as _canonical

from monika.domain.execution.broker_plugin import (
    AccountInfo,
    BrokerPlugin,
    DealData,
    ExitReason,
    InstrumentSpec,
    OrderRequest,
    PluginCategory,
    PluginMetadata,
    PositionData,
    TickData,
    TradingPlugin,
    normalize_order_request,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AccountInfo",
    "BrokerPlugin",
    "DealData",
    "ExitReason",
    "InstrumentSpec",
    "OrderRequest",
    "PluginCategory",
    "PluginMetadata",
    "PositionData",
    "TickData",
    "TradingPlugin",
    "normalize_order_request",
]
