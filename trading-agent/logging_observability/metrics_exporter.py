"""
Compatibility facade shim for legacy metrics_exporter.py.
Re-exports from canonical monika.core.telemetry.metrics_exporter.
"""

from __future__ import annotations

import monika.core.telemetry.metrics_exporter as _canonical

from monika.core.telemetry.metrics_exporter import (
    MetricsCollector,
    metrics,
)

__all__ = ['MetricsCollector', 'metrics']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
