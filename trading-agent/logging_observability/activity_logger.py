"""
Compatibility facade shim for legacy activity_logger.py.
Re-exports from canonical monika.core.telemetry.activity_logger.
"""

from __future__ import annotations

import monika.core.telemetry.activity_logger as _canonical

from monika.core.telemetry.activity_logger import (
    ActivityLogger,
    CATEGORIES,
    DATE_FORMAT,
    LOG_FORMAT_CONSOLE,
    LOG_FORMAT_FILE,
    get_activity_logger,
    setup_logging,
    shutdown_logging,
)

__all__ = ['ActivityLogger', 'CATEGORIES', 'DATE_FORMAT', 'LOG_FORMAT_CONSOLE', 'LOG_FORMAT_FILE', 'get_activity_logger', 'setup_logging', 'shutdown_logging']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
