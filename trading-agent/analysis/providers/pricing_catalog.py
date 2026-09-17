"""
File: trading-agent/analysis/providers/pricing_catalog.py

Centralized AI Model Pricing Catalog.
Re-exports pricing definitions and cost calculations from utils.analytics.pricing,
providing single source of truth for provider pricing lookups.
"""

from typing import Optional, Dict, Any
from utils.analytics.pricing import (
    Price,
    PRICING,
    FREE_TIER_MODELS,
    OPENROUTER_PRICING_MAP,
    infer_provider_from_model,
    is_free_tier,
    get_price,
    cost_usd,
    estimate_cost,
)

__all__ = [
    "Price",
    "PRICING",
    "FREE_TIER_MODELS",
    "OPENROUTER_PRICING_MAP",
    "infer_provider_from_model",
    "is_free_tier",
    "get_price",
    "cost_usd",
    "estimate_cost",
    "get_model_pricing",
    "calculate_cost",
]


def get_model_pricing(model_name: str) -> Price:
    """Lookup Price dataclass for a given model identifier."""
    return get_price(model_name)


def calculate_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    provider: Optional[str] = None,
) -> float:
    """Calculate USD turn cost using production pricing catalog."""
    return cost_usd(
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        provider=provider,
    )
