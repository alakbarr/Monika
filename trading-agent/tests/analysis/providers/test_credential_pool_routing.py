"""
Test suite for APICredentialPool hot-path zero-wait, header-aware cooldowns, and OpenRouter provider routing.
"""

import time
import pytest
from utils.api.credential_pool import APICredentialPool, KeyHealth
from analysis.providers.openrouter_provider import OpenRouterProvider


def test_credential_pool_hot_path_zero_wait():
    pool = APICredentialPool()
    # Add a mock key for test_prov
    pool.add_key("test_prov", "test_key_1")

    # Put key into cooldown
    pool.report_rate_limit("test_prov", "test_key_1", cooldown_seconds=60.0)

    # In regular get_key, it returns None
    assert pool.get_key("test_prov", is_hot_path=False) is None

    # In hot_path get_key, it immediately returns None without delay
    t0 = time.time()
    res = pool.get_key("test_prov", is_hot_path=True)
    t1 = time.time()
    assert res is None
    assert (t1 - t0) < 0.1  # Fast zero-wait return


def test_credential_pool_retry_after_and_reset_at():
    pool = APICredentialPool()
    pool.add_key("test_prov2", "test_key_2")

    # 1. Test retry_after hint
    pool.report_rate_limit("test_prov2", "test_key_2", retry_after=42.0)
    for kh in pool._pools["test_prov2"]:
        if kh.key == "test_key_2":
            rem = kh.cooldown_until - time.time()
            assert 40.0 <= rem <= 43.0

    # 2. Test reset_at hint
    future_time = time.time() + 99.0
    pool.report_rate_limit("test_prov2", "test_key_2", reset_at=future_time)
    for kh in pool._pools["test_prov2"]:
        if kh.key == "test_key_2":
            rem = kh.cooldown_until - time.time()
            assert 95.0 <= rem <= 100.0


def test_openrouter_provider_routing():
    provider = OpenRouterProvider(model="google/gemini-2.5-flash", api_key="sk-or-v1-mock")
    kwargs = {}
    provider._apply_provider_routing(kwargs)

    assert "extra_body" in kwargs
    assert "provider" in kwargs["extra_body"]
    prov_cfg = kwargs["extra_body"]["provider"]
    assert prov_cfg["sort"] == "latency"
    assert prov_cfg["require_parameters"] is True
    assert prov_cfg["data_collection"] == "deny"
