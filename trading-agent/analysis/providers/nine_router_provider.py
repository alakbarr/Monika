# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.nine_router_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.nine_router_provider"""

import sys
import monika.infrastructure.providers.nine_router_provider as _canonical

from monika.infrastructure.providers.nine_router_provider import (
    FREE_TIER_MODELS_9ROUTER,
    NINEROUTER_MODEL_ALIASES,
    NineRouterProvider,
    is_9router_alive,
    logger,
    normalize_9router_model_name,
    try_auto_spawn_9router,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FREE_TIER_MODELS_9ROUTER",
    "NINEROUTER_MODEL_ALIASES",
    "NineRouterProvider",
    "is_9router_alive",
    "logger",
    "normalize_9router_model_name",
    "try_auto_spawn_9router",
]
