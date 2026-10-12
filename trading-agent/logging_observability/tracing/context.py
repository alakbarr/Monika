"""
Compatibility facade shim for legacy context.py.
Re-exports from canonical monika.core.telemetry.tracing.context.
"""

from __future__ import annotations

import monika.core.telemetry.tracing.context as _canonical

from monika.core.telemetry.tracing.context import (
    generate_id,
    generate_trace_id,
    get_baggage,
    get_current_cycle_id,
    get_current_span_id,
    get_current_trace_id,
    set_baggage,
    set_trace_context,
)

__all__ = ['generate_id', 'generate_trace_id', 'get_baggage', 'get_current_cycle_id', 'get_current_span_id', 'get_current_trace_id', 'set_baggage', 'set_trace_context']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
