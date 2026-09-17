"""
Benchmark Pricing compatibility shim.
Re-exports all pricing tables and functions from utils.analytics.pricing.
"""

from utils.analytics.pricing import (
    Price,
    PRICING,
    OPENROUTER_PRICING_MAP,
    FREE_TIER_MODELS,
    get_price,
    cost_usd,
    _FREE,
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
