# ==============================================================================
# File: indicators/order_flow.py
# Description: Backward-compatibility shim for monika.domain.indicators.order_flow
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.order_flow
"""

import sys
import monika.domain.indicators.order_flow as _canonical

from monika.domain.indicators.order_flow import (
    OrderFlowEngine,
    OrderFlowSnapshot,
    fetch_latest_order_flow,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "OrderFlowEngine",
    "OrderFlowSnapshot",
    "fetch_latest_order_flow",
    "logger",
]
