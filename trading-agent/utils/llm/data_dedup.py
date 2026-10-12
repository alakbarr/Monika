"""
Compatibility facade shim for legacy data_dedup.py.
Re-exports from canonical monika.infrastructure.llm.data_dedup.
"""

from __future__ import annotations

import monika.infrastructure.llm.data_dedup as _canonical

from monika.infrastructure.llm.data_dedup import (
    DataFetchDeduplicator,
)

__all__ = ['DataFetchDeduplicator']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
