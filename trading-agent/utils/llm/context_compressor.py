"""
Compatibility facade shim for legacy context_compressor.py.
Re-exports from canonical monika.infrastructure.llm.context_compressor.
"""

from __future__ import annotations

import monika.infrastructure.llm.context_compressor as _canonical

from monika.infrastructure.llm.context_compressor import (
    ContextCompressor,
    TRADING_SUMMARY_SECTIONS,
    get_context_compressor,
    compress_context,
    prune_oversized_tool_results,
    prune_tool_result_content,
    safe_unicode_slice,
    safe_unicode_tail,
    offload_historical_charts,
)

__all__ = ['ContextCompressor', 'TRADING_SUMMARY_SECTIONS', 'get_context_compressor', 'compress_context', 'prune_oversized_tool_results', 'prune_tool_result_content', 'safe_unicode_slice', 'safe_unicode_tail', 'offload_historical_charts']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
