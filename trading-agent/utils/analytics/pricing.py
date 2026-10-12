"""
Compatibility facade shim for legacy pricing.py.
Re-exports from canonical monika.core.analytics.pricing.
"""

from __future__ import annotations

import monika.core.analytics.pricing as _canonical

from monika.core.analytics.pricing import (
    CanonicalUsage,
    FREE_TIER_MODELS,
    Price,
    PricingTier,
    cost_from_canonical,
    cost_usd,
    fetch_openrouter_pricing_async,
    get_price,
    infer_provider_from_model,
    is_free_tier,
)

__all__ = ['CanonicalUsage', 'FREE_TIER_MODELS', 'Price', 'PricingTier', 'cost_from_canonical', 'cost_usd', 'fetch_openrouter_pricing_async', 'get_price', 'infer_provider_from_model', 'is_free_tier']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
