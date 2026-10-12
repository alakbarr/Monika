# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.gemini_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.gemini_provider"""

import sys
import monika.infrastructure.providers.gemini_provider as _canonical

from monika.infrastructure.providers.gemini_provider import (
    GEMINI_MODEL_ALIASES,
    GEMINI_THINKING_LEVEL_MAP,
    GeminiProvider,
    _check_gemini_block,
    _gemini_stream_parser,
    _sanitize_schema_for_gemini,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "GEMINI_MODEL_ALIASES",
    "GEMINI_THINKING_LEVEL_MAP",
    "GeminiProvider",
    "_check_gemini_block",
    "_gemini_stream_parser",
    "_sanitize_schema_for_gemini",
    "logger",
]
