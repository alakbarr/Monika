import pytest
from utils.analytics.pricing import (
    Price,
    PricingTier,
    cost_usd,
    get_price,
    PRICING,
)


def test_pricing_tier_calculation():
    """Verify tiered pricing applies base rate up to threshold and tier rate beyond."""
    tier = PricingTier(
        threshold_tokens=100_000,
        input_rate=1.0,        # Cheaper beyond 100k
        cached_input_rate=0.1,
        output_rate=5.0,
    )
    custom_price = Price(
        input=2.0,            # Standard $2/1M
        cached_input=0.2,
        output=10.0,
        tier=tier,
    )

    PRICING["test-tiered-model"] = custom_price

    try:
        # 1. Under threshold: 50k tokens -> standard rate
        # (50_000 / 1M) * 2.0 = $0.10
        c_under = cost_usd("test-tiered-model", input_tokens=50_000, output_tokens=0)
        assert c_under == 0.10

        # 2. Over threshold: 150k tokens -> 100k @ $2.0/1M + 50k @ $1.0/1M
        # (100k/1M)*2.0 + (50k/1M)*1.0 = 0.20 + 0.05 = $0.25
        c_over = cost_usd("test-tiered-model", input_tokens=150_000, output_tokens=0)
        assert c_over == 0.25
    finally:
        PRICING.pop("test-tiered-model", None)
