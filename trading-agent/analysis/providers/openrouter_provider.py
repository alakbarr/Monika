# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.openrouter_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.openrouter_provider"""

import sys
import monika.infrastructure.providers.openrouter_provider as _canonical

from monika.infrastructure.providers.openrouter_provider import (
    OPENROUTER_MODEL_ALIASES,
    OpenRouterProvider,
    _openrouter_limiter,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "OPENROUTER_MODEL_ALIASES",
    "OpenRouterProvider",
    "_openrouter_limiter",
    "logger",
]
