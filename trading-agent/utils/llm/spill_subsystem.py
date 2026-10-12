"""
Compatibility facade shim for legacy spill_subsystem.py.
Re-exports from canonical monika.infrastructure.llm.spill_subsystem.
"""

from __future__ import annotations

import monika.infrastructure.llm.spill_subsystem as _canonical

from monika.infrastructure.llm.spill_subsystem import (
    PostgresSpillSubsystem,
)

__all__ = ['PostgresSpillSubsystem']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
