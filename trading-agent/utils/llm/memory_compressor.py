"""
Compatibility facade shim for legacy memory_compressor.py.
Re-exports from canonical monika.infrastructure.llm.memory_compressor.
"""

from __future__ import annotations

import monika.infrastructure.llm.memory_compressor as _canonical

from monika.infrastructure.llm.memory_compressor import (
    compress_agent_memory,
)

__all__ = ['compress_agent_memory']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
