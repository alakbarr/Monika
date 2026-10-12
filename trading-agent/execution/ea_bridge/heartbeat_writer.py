# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.ea_bridge.heartbeat_writer
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.ea_bridge.heartbeat_writer"""

import sys
import monika.infrastructure.brokers.ea_bridge.heartbeat_writer as _canonical

from monika.infrastructure.brokers.ea_bridge.heartbeat_writer import (
    EA_HEARTBEAT_FILENAME,
    EA_STALE_THRESHOLD_SECONDS,
    HEARTBEAT_FILENAME,
    HEARTBEAT_INTERVAL_SECONDS,
    HeartbeatManager,
    HeartbeatWriter,
    LEGACY_HEARTBEAT_FILENAME,
    _DEFAULT_MT5_COMMON,
    _get_default_mt5_common,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "EA_HEARTBEAT_FILENAME",
    "EA_STALE_THRESHOLD_SECONDS",
    "HEARTBEAT_FILENAME",
    "HEARTBEAT_INTERVAL_SECONDS",
    "HeartbeatManager",
    "HeartbeatWriter",
    "LEGACY_HEARTBEAT_FILENAME",
    "_DEFAULT_MT5_COMMON",
    "_get_default_mt5_common",
    "logger",
]
