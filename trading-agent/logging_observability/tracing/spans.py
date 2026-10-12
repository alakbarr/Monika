"""
Compatibility facade shim for legacy spans.py.
Re-exports from canonical monika.core.telemetry.tracing.spans.
"""

from __future__ import annotations

import monika.core.telemetry.tracing.spans as _canonical

from monika.core.telemetry.tracing.spans import (
    cycle_span,
    llm_span,
    node_span,
    tool_span,
    trade_span,
)

__all__ = ['cycle_span', 'llm_span', 'node_span', 'tool_span', 'trade_span']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
