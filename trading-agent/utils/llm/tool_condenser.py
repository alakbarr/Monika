"""
Compatibility facade shim for legacy tool_condenser.py.
Re-exports from canonical monika.infrastructure.llm.tool_condenser.
"""

from __future__ import annotations

import monika.infrastructure.llm.tool_condenser as _canonical

from monika.infrastructure.llm.tool_condenser import (
    ToolObservationCondenser,
)

__all__ = ['ToolObservationCondenser']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
