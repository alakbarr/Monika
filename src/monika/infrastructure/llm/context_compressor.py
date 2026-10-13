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

from monika.application.agent.harness.context_compressor import (
    TRADING_SUMMARY_SECTIONS,
    ContextCompressor,
    offload_historical_charts,
    prune_oversized_tool_results,
    prune_tool_result_content,
    safe_unicode_slice,
    safe_unicode_tail,
)

logger = logging.getLogger("TradingAgent.Utils.LLM.ContextCompressor")


class ContextCompressorRuntime:
    """Manages process singleton ContextCompressor instance."""

    compressor: Optional[ContextCompressor] = None

    @classmethod
    def get(cls, settings: Optional[Dict[str, Any]] = None, aux_client: Optional[Any] = None) -> ContextCompressor:
        if cls.compressor is None:
            cls.compressor = ContextCompressor(settings=settings, aux_client=aux_client)
        return cls.compressor

    @classmethod
    def reset(cls) -> None:
        cls.compressor = None


def get_context_compressor(
    settings: Optional[Dict[str, Any]] = None,
    aux_client: Optional[Any] = None,
) -> ContextCompressor:
    """Return process singleton or configured ContextCompressor instance."""
    return ContextCompressorRuntime.get(settings=settings, aux_client=aux_client)


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
