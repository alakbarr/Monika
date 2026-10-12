"""
Unit tests for A/B Paired Strategy Evaluator (Phase 5.3).
"""

import pytest
from benchmark.paired_evaluator import PairedStrategyEvaluator, StrategyMetrics


def test_paired_evaluator_metrics_calculation():
    trades = [
        {"pnl": 100.0},
        {"pnl": 150.0},
        {"pnl": -50.0},
        {"pnl": 200.0},
    ]
    tokens = {"total_tokens": 1500, "cost_usd": 0.0045}
    metrics = PairedStrategyEvaluator._compute_metrics("TestStrategy", trades, tokens)

    assert metrics.total_trades == 4
    assert metrics.winning_trades == 3
    assert metrics.losing_trades == 1
    assert metrics.win_rate == 75.0
    assert metrics.gross_profit == 450.0
    assert metrics.gross_loss == 50.0
    assert metrics.profit_factor == 9.0
    assert metrics.total_tokens == 1500
    assert metrics.total_cost_usd == 0.0045


def test_paired_evaluator_pairwise_comparison():
    evaluator = PairedStrategyEvaluator()

    scenarios = [
        {"scenario_id": "scen_1", "symbol": "EURUSD"},
        {"scenario_id": "scen_2", "symbol": "GBPUSD"},
        {"scenario_id": "scen_3", "symbol": "XAUUSD"},
    ]

    # Baseline: 1 win, 2 losses
    def baseline_fn(scen):
        if scen["scenario_id"] == "scen_1":
            return {"trade": {"pnl": 50.0}, "tokens": 1000, "cost_usd": 0.003}
        return {"trade": {"pnl": -40.0}, "tokens": 1000, "cost_usd": 0.003}

    # Candidate: 2 wins, 1 loss (higher win rate, higher profit factor, less cost)
    def candidate_fn(scen):
        if scen["scenario_id"] in ("scen_1", "scen_2"):
            return {"trade": {"pnl": 80.0}, "tokens": 600, "cost_usd": 0.0018}
        return {"trade": {"pnl": -20.0}, "tokens": 600, "cost_usd": 0.0018}

    report = evaluator.evaluate_pairwise(baseline_fn, candidate_fn, scenarios)

    assert report.baseline.winning_trades == 1
    assert report.candidate.winning_trades == 2
    assert report.win_rate_lift_pct > 0
    assert report.profit_factor_delta > 0
    assert report.token_cost_delta_usd < 0  # Candidate was cheaper
    assert report.is_candidate_superior is True
