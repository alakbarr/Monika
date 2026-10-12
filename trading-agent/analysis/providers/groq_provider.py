# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.groq_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.groq_provider"""

import sys
import monika.infrastructure.providers.groq_provider as _canonical

from monika.infrastructure.providers.groq_provider import (
    GROQ_MODEL_ALIASES,
    GroqProvider,
    _groq_limiter,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "GROQ_MODEL_ALIASES",
    "GroqProvider",
    "_groq_limiter",
    "logger",
]
