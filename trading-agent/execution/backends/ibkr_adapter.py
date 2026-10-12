# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.ibkr_adapter
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.ibkr_adapter"""

import sys
import monika.infrastructure.brokers.ibkr_adapter as _canonical

from monika.infrastructure.brokers.ibkr_adapter import (
    IBKRBrokerAdapter,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "IBKRBrokerAdapter",
    "logger",
]
