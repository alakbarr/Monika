# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.pricing_catalog
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.pricing_catalog"""

import sys
import monika.infrastructure.providers.pricing_catalog as _canonical

from monika.infrastructure.providers.pricing_catalog import (
    FREE_TIER_MODELS,
    OPENROUTER_PRICING_MAP,
    PRICING,
    Price,
    calculate_cost,
    cost_usd,
    estimate_cost,
    get_model_pricing,
    get_price,
    infer_provider_from_model,
    is_free_tier,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FREE_TIER_MODELS",
    "OPENROUTER_PRICING_MAP",
    "PRICING",
    "Price",
    "calculate_cost",
    "cost_usd",
    "estimate_cost",
    "get_model_pricing",
    "get_price",
    "infer_provider_from_model",
    "is_free_tier",
]
