"""
Compatibility facade shim for legacy log_streamer.py.
Re-exports from canonical monika.interfaces.dashboard.log_streamer.
"""

from __future__ import annotations

import monika.interfaces.dashboard.log_streamer as _canonical

from monika.interfaces.dashboard.log_streamer import (
    LOG_LEVEL_ORDER,
    LogStreamer,
    logger,
    parse_log_line_level,
)

__all__ = ['LOG_LEVEL_ORDER', 'LogStreamer', 'logger', 'parse_log_line_level']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
