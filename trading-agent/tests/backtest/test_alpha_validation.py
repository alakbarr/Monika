"""
Unit tests for backtest/alpha_validation.py (directional balance, half-consistency, cost stress).
"""
import pytest
from backtest.alpha_validation import validate_alpha, _calculate_sortino


def test_calculate_sortino():
    # Positive returns with no downside
    assert _calculate_sortino([0.01, 0.02, 0.03]) > 0.0

    # Mixed returns
    sortino = _calculate_sortino([0.02, -0.01, 0.03, -0.005])
    assert sortino > 0.0

    # Strictly negative returns
    assert _calculate_sortino([-0.01, -0.02, -0.015]) < 0.0


def test_validate_alpha_passing():
    trades = [
        {"direction": "BUY", "pnl": 100.0, "pnl_pct": 1.0, "commission": 5.0},
        {"direction": "SELL", "pnl": 50.0, "pnl_pct": 0.5, "commission": 5.0},
        {"direction": "BUY", "pnl": -20.0, "pnl_pct": -0.2, "commission": 5.0},
        {"direction": "SELL", "pnl": 80.0, "pnl_pct": 0.8, "commission": 5.0},
        {"direction": "BUY", "pnl": 40.0, "pnl_pct": 0.4, "commission": 5.0},
        {"direction": "SELL", "pnl": 60.0, "pnl_pct": 0.6, "commission": 5.0},
    ]
    res = validate_alpha(trades)
    assert res.passed is True
    assert res.directional_ok is True
    assert res.half_consistent is True
    assert res.cost_stress_ok is True


def test_validate_alpha_directional_fail():
    # 90% BUY trades -> fails directional balance
    trades = [{"direction": "BUY", "pnl": 10.0, "commission": 1.0}] * 9 + [
        {"direction": "SELL", "pnl": 10.0, "commission": 1.0}
    ]
    res = validate_alpha(trades, max_directional_threshold=0.85)
    assert res.directional_ok is False
    assert res.passed is False


def test_validate_alpha_half_inconsistent():
    # First half very positive, second half consistently negative
    trades = [
        {"direction": "BUY", "pnl": 100.0, "pnl_pct": 1.0, "commission": 1.0},
        {"direction": "SELL", "pnl": 80.0, "pnl_pct": 0.8, "commission": 1.0},
        {"direction": "BUY", "pnl": -50.0, "pnl_pct": -0.5, "commission": 1.0},
        {"direction": "SELL", "pnl": -60.0, "pnl_pct": -0.6, "commission": 1.0},
    ]
    res = validate_alpha(trades)
    assert res.half_consistent is False
    assert res.passed is False


def test_validate_alpha_cost_stress_fail():
    # Marginal profits that turn negative under 2x commissions
    trades = [
        {"direction": "BUY", "pnl": 2.0, "pnl_pct": 0.02, "commission": 3.0},
        {"direction": "SELL", "pnl": 2.0, "pnl_pct": 0.02, "commission": 3.0},
    ]
    # base pnl = 4.0, extra cost under 2x = 3.0 + 3.0 = 6.0, stress pnl = -2.0
    res = validate_alpha(trades, cost_multiplier=2.0)
    assert res.cost_stress_ok is False
    assert res.passed is False
