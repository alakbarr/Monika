"""
Compatibility facade shim for legacy embedding.py.
Re-exports from canonical monika.infrastructure.llm.embedding.
"""

from __future__ import annotations

import monika.infrastructure.llm.embedding as _canonical

from monika.infrastructure.llm.embedding import (
    DEFAULT_EMBEDDING_MODEL,
    GEMINI_EMBEDDING_BASE_URL,
    LEGACY_MODEL_MIGRATIONS,
    generate_gemini_embedding,
)

__all__ = ['DEFAULT_EMBEDDING_MODEL', 'GEMINI_EMBEDDING_BASE_URL', 'LEGACY_MODEL_MIGRATIONS', 'generate_gemini_embedding']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
