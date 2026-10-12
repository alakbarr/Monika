"""
Unit tests for backtest/monte_carlo_engine.py verifying Circular Block Bootstrap and equity compounding.
"""
import pytest
import numpy as np
from backtest.monte_carlo_engine import MonteCarloStressTester


def test_monte_carlo_block_bootstrap():
    """Verify circular block bootstrap mode executes and produces valid drawdown metrics."""
    tester = MonteCarloStressTester(seed=42)
    # Simulated fractional equity returns (e.g. +1.5%, -1.0%, +2.0%, -0.8%)
    trade_returns = [0.015, -0.010, 0.020, -0.008, 0.012, -0.015, 0.005, -0.002] * 5

    res = tester.simulate_trade_sequence(
        trade_returns=trade_returns,
        num_simulations=200,
        initial_equity=10000.0,
        mode="block_bootstrap"
    )

    assert res["num_simulations"] == 200
    assert 0.0 <= res["var_95_drawdown_pct"] <= 100.0
    assert 0.0 <= res["var_99_drawdown_pct"] <= 100.0
    assert res["var_99_drawdown_pct"] >= res["var_95_drawdown_pct"]
    assert res["final_equity_distribution"]["p5"] > 0.0


def test_monte_carlo_equity_compounding_ruin_protection():
    """Verify extreme drawdown doesn't cause imaginary or negative equity numbers."""
    tester = MonteCarloStressTester(seed=42)
    # Catastrophic returns (-80% per trade)
    catastrophic_returns = [-0.80, -0.80, -0.80, -0.80, -0.80]

    res = tester.simulate_trade_sequence(
        trade_returns=catastrophic_returns,
        num_simulations=100,
        initial_equity=10000.0,
        mode="permutation"
    )

    assert res["ruin_probability_pct"] == 100.0
    # Equity must be non-negative
    assert res["final_equity_distribution"]["p5"] >= 0.0
