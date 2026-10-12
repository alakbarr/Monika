# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.ea_bridge.watchdog
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.ea_bridge.watchdog"""

import sys
import monika.infrastructure.brokers.ea_bridge.watchdog as _canonical

from monika.infrastructure.brokers.ea_bridge.watchdog import (
    EAWatchdog,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "EAWatchdog",
    "logger",
]
