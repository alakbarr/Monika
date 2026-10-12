"""
Compatibility facade shim for legacy context_compaction.py.
Re-exports from canonical monika.infrastructure.llm.context_compaction.
"""

from __future__ import annotations

import monika.infrastructure.llm.context_compaction as _canonical

from monika.infrastructure.llm.context_compaction import (
    ContextCompactionEngine,
    spill_tool_output,
)

__all__ = ['ContextCompactionEngine', 'spill_tool_output']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
