# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.openai_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.openai_provider"""

import sys
import monika.infrastructure.providers.openai_provider as _canonical

from monika.infrastructure.providers.openai_provider import (
    OpenAIProvider,
    _canonicalize_schema,
    _extract_message_text,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "OpenAIProvider",
    "_canonicalize_schema",
    "_extract_message_text",
    "logger",
]
