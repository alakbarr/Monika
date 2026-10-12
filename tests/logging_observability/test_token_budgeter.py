"""
Unit tests for TokenBudgetManager in logging_observability/token_budgeter.py.
"""

import pytest
from logging_observability.token_budgeter import TokenBudgetManager, get_token_budgeter


def test_token_budgeter_singleton():
    tb1 = get_token_budgeter({"llm": {"daily_token_budget": 500_000}})
    tb2 = get_token_budgeter()
    assert tb1 is tb2
    assert tb1.daily_budget == 500_000


def test_subsystem_quotas():
    tb = TokenBudgetManager({"llm": {"daily_token_budget": 1_000_000}})
    assert tb.get_quota("stage1") == 200_000
    assert tb.get_quota("stage2") == 450_000
    assert tb.get_quota("debate") == 150_000
    assert tb.get_quota("schedulers") == 100_000
    assert tb.get_quota("reserve") == 100_000


def test_usage_tracking_and_degradation():
    tb = TokenBudgetManager({"llm": {"daily_token_budget": 100_000}})
    # stage1 quota = 20,000
    assert tb.get_degradation_tier("stage1") == "normal"
    assert tb.can_spend("stage1", 5000) is True

    # Spend 15,000 (75% of quota) -> tier becomes compressed
    tb.record_usage("stage1", prompt_tokens=10000, completion_tokens=5000, model="gemini-flash")
    assert tb.get_degradation_tier("stage1") == "compressed"

    # Spend another 3,500 (total 18,500 = 92.5% of quota) -> tier becomes degraded
    tb.record_usage("stage1", prompt_tokens=2000, completion_tokens=1500, model="gemini-flash")
    assert tb.get_degradation_tier("stage1") == "degraded"

    summary = tb.get_budget_summary()
    assert summary["subsystems"]["stage1"]["spent"] == 18500
    assert summary["subsystems"]["stage1"]["tier"] == "degraded"
    assert "gemini-flash" in summary["models"]
