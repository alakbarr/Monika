"""
Benchmark Pricing compatibility shim.
Re-exports all pricing tables and functions from utils.analytics.pricing.
"""

from monika.core.analytics.pricing import (
    _FREE,
    FREE_TIER_MODELS,
    OPENROUTER_PRICING_MAP,
    PRICING,
    Price,
    cost_usd,
    get_price,
)

__all__ = [
    "Price",
    "PRICING",
    "OPENROUTER_PRICING_MAP",
    "FREE_TIER_MODELS",
    "get_price",
    "cost_usd",
    "_FREE",
]
