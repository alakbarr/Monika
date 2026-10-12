"""
Compatibility facade shim for legacy exporters.py.
Re-exports from canonical monika.core.telemetry.tracing.exporters.
"""

from __future__ import annotations

import monika.core.telemetry.tracing.exporters as _canonical

from monika.core.telemetry.tracing.exporters import (
    InMemoryTraceStore,
    TraceRecord,
    global_trace_store,
    logger,
)

__all__ = ['InMemoryTraceStore', 'TraceRecord', 'global_trace_store', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
