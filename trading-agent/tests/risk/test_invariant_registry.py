"""
Unit tests for InvariantRegistry and invariant listeners.
"""

import pytest
from risk.invariants import (
    InvariantRegistry,
    InvariantResult,
    InvariantStatus,
    InvariantViolationError,
    assert_position_count_invariant,
    check_position_count_invariant,
    check_risk_gate_invariant,
)


@pytest.fixture(autouse=True)
def clean_registry():
    InvariantRegistry.reset_instance()
    yield
    InvariantRegistry.reset_instance()


def test_registry_registration_and_listing():
    reg = InvariantRegistry.get_instance()
    assert reg.list_invariants() == []

    reg.register("test_rule", lambda ctx: InvariantResult("test_rule", InvariantStatus.PASS))
    assert reg.list_invariants() == ["test_rule"]

    reg.unregister("test_rule")
    assert reg.list_invariants() == []


def test_registry_run_all_success():
    reg = InvariantRegistry.get_instance()
    reg.register("position_count", check_position_count_invariant)
    reg.register("risk_gate", check_risk_gate_invariant)

    context = {
        "open_positions": [{"ticket": 123}, {"ticket": 124}],
        "max_concurrent_positions": 5,
        "proposal": {
            "action": "buy",
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "take_profit": 120.0,
        },
        "current_drawdown_pct": 1.5,
        "max_drawdown_limit": 3.0,
        "min_rr_ratio": 1.0,
    }

    results = reg.run_all(context)
    assert len(results) == 2
    assert all(r.passed for r in results)

    # assert_all should not raise
    reg.assert_all(context)


def test_position_count_invariant_failure():
    # Direct function
    with pytest.raises(InvariantViolationError, match="Position count breach"):
        assert_position_count_invariant([1, 2, 3, 4, 5, 6], max_concurrent_positions=5)

    # Adapter
    context = {"open_positions": [1, 2, 3, 4, 5, 6], "max_concurrent_positions": 5}
    res = check_position_count_invariant(context)
    assert res.failed
    assert "exceed allowed limit" in res.message


def test_position_count_invariant_warning_at_cap():
    context = {"open_positions": [1, 2, 3, 4, 5], "max_concurrent_positions": 5}
    res = check_position_count_invariant(context)
    assert res.status == InvariantStatus.WARN
    assert "maximum capacity" in res.message


def test_registry_assert_all_raises_on_failure():
    reg = InvariantRegistry.get_instance()
    reg.register("position_count", check_position_count_invariant)
    reg.register("risk_gate", check_risk_gate_invariant)

    # Breach drawdown limit (4.0% > 3.0%)
    context = {
        "open_positions": [1],
        "proposal": {"action": "buy", "entry_price": 100, "stop_loss": 90, "take_profit": 120},
        "current_drawdown_pct": 4.0,
        "max_drawdown_limit": 3.0,
    }

    with pytest.raises(InvariantViolationError, match="Drawdown ceiling breach"):
        reg.assert_all(context)


def test_registry_fail_fast():
    reg = InvariantRegistry.get_instance()
    reg.register("position_count", check_position_count_invariant)

    context = {"open_positions": [1, 2, 3, 4], "max_concurrent_positions": 2}
    with pytest.raises(InvariantViolationError, match="Invariant failure in 'position_count'"):
        reg.run_all(context, fail_fast=True)
