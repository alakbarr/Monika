# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.deepseek_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.deepseek_provider"""

import sys
import monika.infrastructure.providers.deepseek_provider as _canonical

from monika.infrastructure.providers.deepseek_provider import (
    DeepSeekProvider,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DeepSeekProvider",
    "logger",
]
