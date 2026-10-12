"""
Compatibility facade shim for legacy delegation_live_log.py.
Re-exports from canonical monika.core.telemetry.delegation_live_log.
"""

from __future__ import annotations

import monika.core.telemetry.delegation_live_log as _canonical

from monika.core.telemetry.delegation_live_log import (
    DEFAULT_LOG_DIR,
    LiveTranscriptWriter,
    logger,
)

__all__ = ['DEFAULT_LOG_DIR', 'LiveTranscriptWriter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
