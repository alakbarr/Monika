"""
Compatibility facade shim for legacy semantic_cache.py.
Re-exports from canonical monika.infrastructure.llm.semantic_cache.
"""

from __future__ import annotations

import monika.infrastructure.llm.semantic_cache as _canonical

from monika.infrastructure.llm.semantic_cache import (
    TradingSemanticCache,
)

__all__ = ['TradingSemanticCache']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
