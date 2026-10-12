"""
Compatibility facade shim for legacy academic_search.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.academic_search.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.academic_search as _canonical

from monika.infrastructure.data_ingestion.sources.academic_search import (
    ARXIV_API_URL,
    ATOM_NS,
    AcademicSearchClient,
    logger,
)

__all__ = ['ARXIV_API_URL', 'ATOM_NS', 'AcademicSearchClient', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
