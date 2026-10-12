"""
Compatibility facade shim for legacy web_search.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.web_search.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.web_search as _canonical

from monika.infrastructure.data_ingestion.sources.web_search import (
    SearchMemo,
    WebSearch,
    WebSearchService,
    _global_web_search_service,
    get_web_search_service,
    logger,
)

__all__ = ['SearchMemo', 'WebSearch', 'WebSearchService', '_global_web_search_service', 'get_web_search_service', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
