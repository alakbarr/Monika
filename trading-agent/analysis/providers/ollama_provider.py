# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.ollama_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.ollama_provider"""

import sys
import monika.infrastructure.providers.ollama_provider as _canonical

from monika.infrastructure.providers.ollama_provider import (
    OllamaProvider,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "OllamaProvider",
    "logger",
]
