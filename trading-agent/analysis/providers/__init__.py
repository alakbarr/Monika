# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers"""

import sys
import monika.infrastructure.providers as _canonical

from monika.infrastructure.providers import (
    BaseLLMClient,
    MODEL_CAPABILITIES,
    MockBlock,
    MockResponse,
    ModelCapabilities,
    get_model_capabilities,
)

__all__ = [
    "BaseLLMClient",
    "MODEL_CAPABILITIES",
    "MockBlock",
    "MockResponse",
    "ModelCapabilities",
    "get_model_capabilities",
]
