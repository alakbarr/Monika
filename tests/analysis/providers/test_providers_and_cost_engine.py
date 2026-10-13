# ==============================================================================
# File: tests/analysis/providers/test_phase4_providers_and_cost_engine.py
# ==============================================================================

import pytest
import time
from pathlib import Path
from decimal import Decimal

from provider.credential_pool import CredentialPool, KeyHealth, CredentialStatus
from analysis.providers.capabilities import (
    resolve_stale_timeout_floor,
    clamp_reasoning_effort,
    get_model_capabilities,
)
from utils.analytics.pricing import (
    Price,
    CanonicalUsage,
    cost_usd,
    cost_from_canonical,
    fetch_openrouter_pricing_async,
)


def test_credential_pool_sole_credential_clamping():
    """Verify that a provider with only one active key clamps rate limit cooldown to max 60s."""
    pool = CredentialPool(base_cooldown_seconds=60.0, max_cooldown_seconds=14400.0, auto_init_env=False)
    pool.add_key("openai", "sk-single-openai-key-123456789012")

    # Single key rate limit
    cd = pool.report_rate_limit("openai", "sk-single-openai-key-123456789012", cooldown_seconds=300.0)
    # Because it is a sole credential, cooldown is clamped to max 60s
    assert cd <= 60.0

    # Model-level rate limit
    pool.mark_model_rate_limited("openai", "o3-mini", cooldown_seconds=45.0)
    key_obj = pool._pools["openai"][0]
    assert "o3-mini" in key_obj.model_cooldowns

    # Validate entitlement
    assert pool.validate_entitlement("sk-single-openai-key-123456789012") is True


def test_stale_timeout_floor_resolution():
    """Verify that reasoning models get minimum timeout floors of 180s - 300s."""
    # Standard fast models
    assert resolve_stale_timeout_floor("gemini-3.5-flash-lite", default_timeout=30.0) == 30.0
    assert resolve_stale_timeout_floor("gpt-4o-mini", default_timeout=25.0) == 25.0

    # Frontier reasoning models
    assert resolve_stale_timeout_floor("o1", default_timeout=30.0) >= 180.0
    assert resolve_stale_timeout_floor("claude-3-7-sonnet-thinking", default_timeout=30.0) >= 180.0
    assert resolve_stale_timeout_floor("deepseek-reasoner", default_timeout=30.0) >= 300.0
    assert resolve_stale_timeout_floor("o3", default_timeout=30.0) >= 300.0


def test_clamp_reasoning_effort():
    """Verify reasoning effort parameter normalization."""
    assert clamp_reasoning_effort("o3-mini", "high") == "high"
    assert clamp_reasoning_effort("o3-mini", "LOW") == "low"
    assert clamp_reasoning_effort("o3-mini", "invalid_effort") == "medium"
    assert clamp_reasoning_effort("o1-mini", "high") == "medium"


def test_decimal_pricing_and_cache_write_split():
    """Verify institutional decimal cost accounting and cache write split."""
    # Test Price effective cache write
    p = Price(input=3.00, cached_input=0.30, output=15.00)
    assert p.effective_cache_write == 3.75  # 1.25x of 3.00

    # Standard call with uncached input, cached read, and output
    cost = cost_usd(
        model_name="claude-3-5-sonnet",
        input_tokens=10000,
        output_tokens=2000,
        cached_tokens=50000,
    )
    assert isinstance(cost, float)
    assert cost > 0.0

    # CanonicalUsage with cache creation / write tokens
    usage = CanonicalUsage(
        input_tokens=5000,
        output_tokens=1000,
        cache_read_tokens=20000,
        cache_creation_tokens=10000,
    )
    cost_canonical = cost_from_canonical("claude-3-7-sonnet", usage)
    assert cost_canonical > 0.0


@pytest.mark.asyncio
async def test_fetch_openrouter_pricing_fallback(tmp_path: Path):
    """Verify live pricing fetcher disk cache and static fallback."""
    cache_file = tmp_path / "openrouter_pricing.json"
    res = await fetch_openrouter_pricing_async(cache_path=str(cache_file))
    assert isinstance(res, dict)
    assert len(res) > 0
