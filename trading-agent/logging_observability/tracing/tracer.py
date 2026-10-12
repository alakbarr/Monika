"""
Compatibility facade shim for legacy tracer.py.
Re-exports from canonical monika.core.telemetry.tracing.tracer.
"""

from __future__ import annotations

import monika.core.telemetry.tracing.tracer as _canonical

from monika.core.telemetry.tracing.tracer import (
    AgentTracer,
    Span,
    get_tracer,
    logger,
)

__all__ = ['AgentTracer', 'Span', 'get_tracer', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
