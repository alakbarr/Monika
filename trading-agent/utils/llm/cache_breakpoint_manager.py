"""
Compatibility facade shim for legacy cache_breakpoint_manager.py.
Re-exports from canonical monika.infrastructure.llm.cache_breakpoint_manager.
"""

from __future__ import annotations

import monika.infrastructure.llm.cache_breakpoint_manager as _canonical

from monika.infrastructure.llm.cache_breakpoint_manager import (
    CacheBreakpointManager,
)

__all__ = ['CacheBreakpointManager']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
