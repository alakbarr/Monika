"""
Compatibility facade shim for legacy prompt_caching.py.
Re-exports from canonical monika.infrastructure.llm.prompt_caching.
"""

from __future__ import annotations

import monika.infrastructure.llm.prompt_caching as _canonical

from monika.infrastructure.llm.prompt_caching import (
    PromptCacheManager,
    PromptCacheTracker,
)

__all__ = ['PromptCacheManager', 'PromptCacheTracker']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
