# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.runtime_model_registry
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.runtime_model_registry"""

import sys
import monika.infrastructure.providers.runtime_model_registry as _canonical

from monika.infrastructure.providers.runtime_model_registry import (
    RuntimeModelRegistry,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "RuntimeModelRegistry",
    "logger",
]
