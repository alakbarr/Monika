# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.event_store
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.event_store"""

import sys
import monika.infrastructure.database.event_store as _canonical

from monika.infrastructure.database.event_store import (
    TradingEventStore,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "TradingEventStore",
    "logger",
]
