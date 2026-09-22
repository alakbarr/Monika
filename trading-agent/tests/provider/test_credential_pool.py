"""
Unit tests for Monika v2 Credential Pool & Multi-Key Health Tracker (provider/credential_pool.py).
Tests exponential cooldown backoff, FailoverReason integration, cost tracking, and model-level isolation.
"""

import time
import pytest
from provider.credential_pool import (
    CredentialPool,
    APICredentialPool,
    LLMCredentialPool,
    KeyHealth,
    get_credential_pool,
)
from provider.error_taxonomy import FailoverReason


def test_credential_pool_exponential_backoff():
    pool = CredentialPool(base_cooldown_seconds=60.0, max_cooldown_seconds=14400.0, auto_init_env=False)
    pool.add_key("gemini", "mock_key_alpha")

    # 1st rate limit: 60s
    cd1 = pool.report_rate_limit("gemini", "mock_key_alpha")
    assert cd1 == 60.0

    # 2nd consecutive rate limit: 120s
    cd2 = pool.report_rate_limit("gemini", "mock_key_alpha")
    assert cd2 == 120.0

    # 3rd consecutive rate limit: 240s
    cd3 = pool.report_rate_limit("gemini", "mock_key_alpha")
    assert cd3 == 240.0

    # Success resets consecutive rate limits
    pool.report_success("gemini", "mock_key_alpha")
    for kh in pool._pools["gemini"]:
        if kh.key == "mock_key_alpha":
            assert kh.consecutive_rate_limits == 0
            assert kh.consecutive_errors == 0


def test_credential_pool_permanent_failure():
    pool = CredentialPool(auto_init_env=False)
    pool.add_key("openai", "mock_key_bad_auth")

    # Reporting auth failure permanently disables key
    pool.report_failure("openai", "mock_key_bad_auth", reason=FailoverReason.AUTH_PERMANENT)
    
    for kh in pool._pools["openai"]:
        if kh.key == "mock_key_bad_auth":
            assert kh.is_active is False
            assert "auth" in str(kh.disabled_reason).lower()

    # Unavailable for get_key
    assert pool.get_key("openai") is None
    assert pool.all_exhausted("openai") is True


def test_credential_pool_cost_tracking():
    pool = CredentialPool(auto_init_env=False)
    pool.add_key("anthropic", "mock_key_claude")

    # Report success with tokens and cost
    pool.report_success("anthropic", "mock_key_claude", tokens=1500, cost_usd=0.045)
    pool.report_success("anthropic", "mock_key_claude", tokens=2500, cost_usd=0.075)

    assert pool.get_cumulative_cost("anthropic") == pytest.approx(0.120, rel=1e-3)
    assert pool.get_cumulative_cost() == pytest.approx(0.120, rel=1e-3)

    status = pool.get_pool_status("anthropic")
    assert len(status["anthropic"]) == 1
    assert status["anthropic"][0]["total_tokens"] == 4000
    assert status["anthropic"][0]["total_cost_usd"] == pytest.approx(0.120, rel=1e-3)


def test_credential_pool_model_level_cooldown():
    pool = CredentialPool(auto_init_env=False)
    pool.add_key("deepseek", "mock_key_ds")

    # Rate limit only for "deepseek-r1", keep "deepseek-chat" available
    pool.report_rate_limit("deepseek", "mock_key_ds", cooldown_seconds=60.0, model="deepseek-r1")

    assert pool.is_model_available("deepseek-r1", provider="deepseek") is False
    assert pool.is_model_available("deepseek-chat", provider="deepseek") is True

    # get_key filters by model availability
    assert pool.get_key("deepseek", model="deepseek-r1") is None
    assert pool.get_key("deepseek", model="deepseek-chat") == "mock_key_ds"


def test_credential_pool_hot_path_zero_wait():
    pool = CredentialPool(auto_init_env=False)
    pool.add_key("groq", "mock_key_groq")
    pool.report_rate_limit("groq", "mock_key_groq", cooldown_seconds=100.0)

    t0 = time.time()
    key = pool.get_key("groq", is_hot_path=True)
    t1 = time.time()

    assert key is None
    assert (t1 - t0) < 0.1


@pytest.mark.asyncio
async def test_llm_credential_pool_async_rotation():
    pool = LLMCredentialPool(provider="gemini", keys=["key_a", "key_b"])
    assert pool.total_keys() == 2

    k1 = await pool.get_active_key()
    assert k1 in ("key_a", "key_b")

    await pool.report_rate_limited(k1, cooldown_seconds=30.0)
    k2 = await pool.get_active_key()
    assert k2 != k1
    assert k2 in ("key_a", "key_b")
