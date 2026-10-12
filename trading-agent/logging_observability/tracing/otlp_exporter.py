"""
Compatibility facade shim for legacy otlp_exporter.py.
Re-exports from canonical monika.core.telemetry.tracing.otlp_exporter.
"""

from __future__ import annotations

import monika.core.telemetry.tracing.otlp_exporter as _canonical

from monika.core.telemetry.tracing.otlp_exporter import (
    OTLPSpanExporter,
    global_otlp_exporter,
    logger,
)

__all__ = ['OTLPSpanExporter', 'global_otlp_exporter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
