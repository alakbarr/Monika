"""
Compatibility facade shim for legacy llmlingua_compressor.py.
Re-exports from canonical monika.infrastructure.llm.llmlingua_compressor.
"""

from __future__ import annotations

import monika.infrastructure.llm.llmlingua_compressor as _canonical

from monika.infrastructure.llm.llmlingua_compressor import (
    AdaptiveLLMLinguaCompressor,
)

__all__ = ['AdaptiveLLMLinguaCompressor']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
