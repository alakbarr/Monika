"""
Compatibility facade shim for legacy report_writer.py.
Re-exports from canonical monika.core.telemetry.report_writer.
"""

from __future__ import annotations

import monika.core.telemetry.report_writer as _canonical

from monika.core.telemetry.report_writer import (
    ReportWriter,
)

__all__ = ['ReportWriter']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
