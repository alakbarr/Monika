"""
Declarative model capability table for multi-provider LLM integration.
Consolidated single source of truth forwarding to monika.infrastructure.providers.capabilities.
"""

from __future__ import annotations

from monika.infrastructure.providers.capabilities import (
    DEFAULT_CAPABILITIES,
    MODEL_CAPABILITIES,
    ModelCapabilities,
    get_capabilities,
    get_model_capabilities,
    resolve_effective_context_window,
)

__all__ = [
    "ModelCapabilities",
    "MODEL_CAPABILITIES",
    "DEFAULT_CAPABILITIES",
    "get_capabilities",
    "get_model_capabilities",
    "resolve_effective_context_window",
]
