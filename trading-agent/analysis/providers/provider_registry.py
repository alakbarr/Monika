# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.provider_registry
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.provider_registry"""

import sys
import monika.infrastructure.providers.provider_registry as _canonical

from monika.infrastructure.providers.provider_registry import (
    LLMProviderPlugin,
    ProviderRegistry,
    _register_builtins,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "LLMProviderPlugin",
    "ProviderRegistry",
    "_register_builtins",
    "logger",
]
