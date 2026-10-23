"""
File: src/monika/infrastructure/providers/pricing_catalog.py

Centralized AI Model Pricing Catalog.
Re-exports pricing definitions and cost calculations from utils.analytics.pricing,
providing single source of truth for provider pricing lookups.
"""

from decimal import Decimal
from typing import Any, Dict, Optional

from monika.core.analytics.pricing import (
    FREE_TIER_MODELS,
    OPENROUTER_PRICING_MAP,
    PRICING,
    Price,
    cost_decimal_from_canonical,
    cost_from_canonical,
    cost_usd,
    cost_usd_decimal,
    estimate_cost,
    get_price,
    infer_provider_from_model,
    is_free_tier,
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
    "cost_usd_decimal",
    "cost_from_canonical",
    "cost_decimal_from_canonical",
    "estimate_cost",
    "get_model_pricing",
    "calculate_cost",
    "calculate_cost_decimal",
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


def calculate_cost_decimal(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    provider: Optional[str] = None,
) -> Decimal:
    """Calculate USD turn cost with institutional Decimal precision."""
    return cost_usd_decimal(
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        provider=provider,
    )
