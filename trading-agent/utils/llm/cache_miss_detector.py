"""
Compatibility facade shim for legacy cache_miss_detector.py.
Re-exports from canonical monika.infrastructure.llm.cache_miss_detector.
"""

from __future__ import annotations

import monika.infrastructure.llm.cache_miss_detector as _canonical

from monika.infrastructure.llm.cache_miss_detector import (
    CACHE_TTL_MS,
    CacheMissDetector,
    CacheMissReport,
    global_cache_miss_detector,
)

__all__ = ['CACHE_TTL_MS', 'CacheMissDetector', 'CacheMissReport', 'global_cache_miss_detector']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
