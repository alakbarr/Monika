# ==============================================================================
# File: utils/llm/context_compressor.py
# ==============================================================================

"""
Unified Context Compressor & Memory Compaction Facade (Phase 4).
Canonical entrypoint consolidating multi-phase hierarchical context compression,
deterministic tool pruning, boundary splitting, and auxiliary summarization.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from monika.application.analysis.harness.context_compressor import (
    ContextCompressor,
    TRADING_SUMMARY_SECTIONS,
    prune_oversized_tool_results,
    prune_tool_result_content,
    safe_unicode_slice,
    safe_unicode_tail,
    offload_historical_charts,
)

logger = logging.getLogger("TradingAgent.Utils.LLM.ContextCompressor")


_GLOBAL_COMPRESSOR: Optional[ContextCompressor] = None


def get_context_compressor(
    settings: Optional[Dict[str, Any]] = None,
    aux_client: Optional[Any] = None,
) -> ContextCompressor:
    """Return process singleton or configured ContextCompressor instance."""
    global _GLOBAL_COMPRESSOR
    if _GLOBAL_COMPRESSOR is None:
        _GLOBAL_COMPRESSOR = ContextCompressor(settings=settings, aux_client=aux_client)
    return _GLOBAL_COMPRESSOR


async def compress_context(
    messages: List[Dict[str, Any]],
    max_context_chars: int = 100000,
    tail_turns: int = 3,
    settings: Optional[Dict[str, Any]] = None,
    aux_client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to compress messages list using canonical ContextCompressor.
    Applies deterministic tool pruning, protected boundary preservation, and summarization.
    """
    compressor = get_context_compressor(settings=settings, aux_client=aux_client)
    return await compressor.compress(
        messages=messages,
        max_context_chars=max_context_chars,
        tail_turns=tail_turns,
    )


__all__ = [
    "ContextCompressor",
    "TRADING_SUMMARY_SECTIONS",
    "get_context_compressor",
    "compress_context",
    "prune_oversized_tool_results",
    "prune_tool_result_content",
    "safe_unicode_slice",
    "safe_unicode_tail",
    "offload_historical_charts",
]
