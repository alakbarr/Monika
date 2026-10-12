# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.streaming_think_scrubber
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.streaming_think_scrubber"""

import sys
import monika.infrastructure.providers.streaming_think_scrubber as _canonical

from monika.infrastructure.providers.streaming_think_scrubber import (
    DEFAULT_REASONING_TAG_PAIRS,
    StreamingThinkScrubber,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_REASONING_TAG_PAIRS",
    "StreamingThinkScrubber",
    "logger",
]
