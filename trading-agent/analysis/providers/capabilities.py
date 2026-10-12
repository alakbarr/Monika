# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.capabilities
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.capabilities"""

import sys
import monika.infrastructure.providers.capabilities as _canonical

from monika.infrastructure.providers.capabilities import (
    DEFAULT_CAPABILITIES,
    MODEL_CAPABILITIES,
    ModelCapabilities,
    clamp_reasoning_effort,
    get_capabilities,
    get_model_capabilities,
    resolve_effective_context_window,
    resolve_stale_timeout_floor,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_CAPABILITIES",
    "MODEL_CAPABILITIES",
    "ModelCapabilities",
    "clamp_reasoning_effort",
    "get_capabilities",
    "get_model_capabilities",
    "resolve_effective_context_window",
    "resolve_stale_timeout_floor",
]
