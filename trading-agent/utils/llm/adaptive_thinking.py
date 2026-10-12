"""
Compatibility facade shim for legacy adaptive_thinking.py.
Re-exports from canonical monika.infrastructure.llm.adaptive_thinking.
"""

from __future__ import annotations

import monika.infrastructure.llm.adaptive_thinking as _canonical

from monika.infrastructure.llm.adaptive_thinking import (
    PerSymbolAdaptiveThinkingAllocator,
    QuantizedThinkingAllocator,
)

__all__ = ['PerSymbolAdaptiveThinkingAllocator', 'QuantizedThinkingAllocator']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
