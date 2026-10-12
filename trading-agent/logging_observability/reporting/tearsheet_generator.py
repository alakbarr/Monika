"""
Compatibility facade shim for legacy tearsheet_generator.py.
Re-exports from canonical monika.core.telemetry.reporting.tearsheet_generator.
"""

from __future__ import annotations

import monika.core.telemetry.reporting.tearsheet_generator as _canonical

from monika.core.telemetry.reporting.tearsheet_generator import (
    QuantTearsheetGenerator,
    TearsheetResult,
    logger,
)

__all__ = ['QuantTearsheetGenerator', 'TearsheetResult', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
