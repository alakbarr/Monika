# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.llm_factory
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.llm_factory"""

import sys
import monika.infrastructure.providers.llm_factory as _canonical

from monika.infrastructure.providers.llm_factory import (
    EndpointBlackhole,
    FallbackClientWrapper,
    HOT_PATH_ROLES,
    LLMFactory,
    ProviderCircuitBreaker,
    _UNSUPPORTED_SCHEMA_ROUTES,
    _safe_clone,
    create_client,
    get_client_for_task,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "EndpointBlackhole",
    "FallbackClientWrapper",
    "HOT_PATH_ROLES",
    "LLMFactory",
    "ProviderCircuitBreaker",
    "_UNSUPPORTED_SCHEMA_ROUTES",
    "_safe_clone",
    "create_client",
    "get_client_for_task",
    "logger",
]
