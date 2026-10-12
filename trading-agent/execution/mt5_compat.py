# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.mt5_compat
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.mt5_compat"""

import sys
import monika.infrastructure.brokers.mt5_compat as _canonical

from monika.infrastructure.brokers.mt5_compat import (
    MT5BridgeProxy,
    MT5FallbackModule,
    MT5_CONSTANTS,
    _active_mt5_module,
    ensure_mt5_module,
    get_mt5_module,
    is_mt5linux_available,
    is_native_mt5_available,
    logger,
    mt5,
)

sys.modules[__name__] = _canonical

__all__ = [
    "MT5BridgeProxy",
    "MT5FallbackModule",
    "MT5_CONSTANTS",
    "_active_mt5_module",
    "ensure_mt5_module",
    "get_mt5_module",
    "is_mt5linux_available",
    "is_native_mt5_available",
    "logger",
    "mt5",
]
