import pytest
from utils.llm.cycle_budget_guard import CycleBudgetGuard, get_cycle_budget_guard


def test_cycle_budget_guard_defaults():
    guard = CycleBudgetGuard(max_input_tokens=1000, max_output_tokens=200, max_cost_usd=1.0)
    assert guard.is_exceeded() is False

    guard.record(input_tokens=500, output_tokens=100, cost_usd=0.2)
    allowed, reason = guard.check()
    assert allowed is True
    assert reason == "ok"
    assert guard.is_exceeded() is False

    stats = guard.get_stats()
    assert stats["input_used"] == 500
    assert stats["output_used"] == 100
    assert stats["total_tokens"] == 600
    assert stats["cost_usd_used"] == 0.2


def test_cycle_budget_guard_input_exceeded():
    guard = CycleBudgetGuard(max_input_tokens=1000, max_output_tokens=200, max_cost_usd=1.0)
    guard.record(input_tokens=1200, output_tokens=50)

    allowed, reason = guard.check()
    assert allowed is False
    assert "Input token budget exceeded" in reason
    assert guard.is_exceeded() is True


def test_cycle_budget_guard_output_exceeded():
    guard = CycleBudgetGuard(max_input_tokens=1000, max_output_tokens=200, max_cost_usd=1.0)
    guard.record(input_tokens=500, output_tokens=250)

    allowed, reason = guard.check()
    assert allowed is False
    assert "Output token budget exceeded" in reason
    assert guard.is_exceeded() is True


def test_cycle_budget_guard_cost_exceeded():
    guard = CycleBudgetGuard(max_input_tokens=10000, max_output_tokens=2000, max_cost_usd=0.50)
    guard.record(input_tokens=500, output_tokens=200, cost_usd=0.75)

    allowed, reason = guard.check()
    assert allowed is False
    assert "Cost budget exceeded" in reason
    assert guard.is_exceeded() is True


def test_cycle_budget_guard_reset():
    guard = CycleBudgetGuard(max_input_tokens=100, max_output_tokens=50)
    guard.record(input_tokens=150, output_tokens=60)
    assert guard.is_exceeded() is True

    guard.reset()
    assert guard.is_exceeded() is False
    stats = guard.get_stats()
    assert stats["input_used"] == 0
    assert stats["output_used"] == 0


def test_cycle_budget_guard_from_settings():
    settings = {
        "llm": {
            "cycle_budget": {
                "max_input_tokens": 50000,
                "max_output_tokens": 10000,
                "max_cost_usd": 2.5,
                "enabled": True,
            }
        }
    }
    guard = CycleBudgetGuard.from_settings(settings)
    assert guard.max_input_tokens == 50000
    assert guard.max_output_tokens == 10000
    assert guard.max_cost_usd == 2.5
    assert guard.enabled is True
