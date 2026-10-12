"""
Compatibility facade shim for legacy doctor.py.
Re-exports from canonical monika.interfaces.cli.doctor.
"""

from __future__ import annotations

import monika.interfaces.cli.doctor as _canonical

from monika.interfaces.cli.doctor import (
    DiagnosticItem,
    SystemDoctor,
    logger,
)

__all__ = ['DiagnosticItem', 'SystemDoctor', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
