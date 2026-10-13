"""
Backward-compatibility facade for ContextCompressor.
Canonical location: monika.application.agent.harness.context_compressor
"""

import sys
import monika.application.agent.harness.context_compressor as _canonical

from monika.application.agent.harness.context_compressor import (
    TOOL_PRUNE_MARKER,
    TRADING_SUMMARY_SECTIONS,
    ContextCompressor,
    offload_historical_charts,
    prune_oversized_tool_results,
    prune_tool_result_content,
    safe_unicode_slice,
    safe_unicode_tail,
)

__all__ = [
    "ContextCompressor",
    "TRADING_SUMMARY_SECTIONS",
    "TOOL_PRUNE_MARKER",
    "offload_historical_charts",
    "prune_oversized_tool_results",
    "prune_tool_result_content",
    "safe_unicode_slice",
    "safe_unicode_tail",
]

sys.modules[__name__] = _canonical
