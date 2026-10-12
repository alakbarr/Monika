# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.anthropic_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.anthropic_provider"""

import sys
import monika.infrastructure.providers.anthropic_provider as _canonical

from monika.infrastructure.providers.anthropic_provider import (
    AnthropicProvider,
    _build_system_blocks,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AnthropicProvider",
    "_build_system_blocks",
    "logger",
]
