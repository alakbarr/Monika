"""
Tests for PR-12: Eval Metrics & A/B Evaluation Harness.
Verifies directional accuracy, Brier scoring, token cost efficiency,
and A/B comparison logic across baseline and candidate variants.
"""

import pytest
from evals.eval_metrics import (
    DecisionEvaluation,
    AggregateMetrics,
    compute_brier_score,
    aggregate_eval_metrics,
    compare_ab_evaluations,
)
from evals.eval_runner import ABEvalRunner
from evals.runner import get_default_golden_candidates


def test_brier_score_calculation():
    # Perfectly calibrated decisions
    decisions = [
        DecisionEvaluation(
            scenario_id="1", symbol="EURUSD", decision="BUY",
            is_valid_direction=True, confluence_score=100.0, oracle_passed=True
        ),
        DecisionEvaluation(
            scenario_id="2", symbol="USDJPY", decision="WAIT",
            is_valid_direction=False, confluence_score=0.0, oracle_passed=True
        ),
    ]
    score = compute_brier_score(decisions)
    assert score == 0.0

    # Completely uncalibrated decisions
    uncalibrated = [
        DecisionEvaluation(
            scenario_id="1", symbol="EURUSD", decision="BUY",
            is_valid_direction=False, confluence_score=100.0, oracle_passed=False
        ),
    ]
    bad_score = compute_brier_score(uncalibrated)
    assert bad_score == 1.0


def test_aggregate_eval_metrics():
    decisions = [
        DecisionEvaluation(
            scenario_id="1", symbol="EURUSD", decision="BUY",
            is_valid_direction=True, confluence_score=80.0,
            grounding_passed=True, oracle_passed=True, planned_rr=1.5,
            input_tokens=100, output_tokens=50, cost_usd=0.001, latency_ms=500.0
        ),
        DecisionEvaluation(
            scenario_id="2", symbol="USDJPY", decision="SELL",
            is_valid_direction=False, confluence_score=60.0,
            grounding_passed=False, oracle_passed=False, planned_rr=2.0,
            input_tokens=120, output_tokens=60, cost_usd=0.0012, latency_ms=600.0
        ),
    ]
    agg = aggregate_eval_metrics(decisions)
    assert agg.total_scenarios == 2
    assert agg.valid_direction_count == 1
    assert agg.directional_accuracy_pct == 50.0
    assert agg.grounding_pass_rate_pct == 50.0
    assert agg.oracle_pass_rate_pct == 50.0
    assert agg.avg_planned_rr == 1.75
    assert agg.total_tokens == 330
    assert agg.avg_latency_ms == 550.0


def test_compare_ab_evaluations_promotion():
    baseline = [
        DecisionEvaluation(
            scenario_id="1", symbol="EURUSD", decision="BUY",
            is_valid_direction=True, confluence_score=80.0,
            grounding_passed=True, oracle_passed=True,
            input_tokens=500, output_tokens=100, cost_usd=0.005, latency_ms=1000.0
        ),
    ]
    # Candidate has same accuracy but 40% token savings
    candidate = [
        DecisionEvaluation(
            scenario_id="1", symbol="EURUSD", decision="BUY",
            is_valid_direction=True, confluence_score=85.0,
            grounding_passed=True, oracle_passed=True,
            input_tokens=300, output_tokens=60, cost_usd=0.003, latency_ms=700.0
        ),
    ]
    report = compare_ab_evaluations(baseline, candidate, name="DSH Context Optimization")
    assert report.token_savings_pct == 40.0
    assert report.cost_savings_pct == 40.0
    assert report.recommendation == "PROMOTE"
    assert "A/B Evaluation Report" in report.summary_markdown


def test_compare_ab_evaluations_rejection():
    baseline = [
        DecisionEvaluation(
            scenario_id="1", symbol="EURUSD", decision="BUY",
            is_valid_direction=True, confluence_score=80.0,
            grounding_passed=True, oracle_passed=True
        ),
    ]
    # Candidate fails directional accuracy
    candidate = [
        DecisionEvaluation(
            scenario_id="1", symbol="EURUSD", decision="SELL",
            is_valid_direction=False, confluence_score=80.0,
            grounding_passed=True, oracle_passed=False
        ),
    ]
    report = compare_ab_evaluations(baseline, candidate, name="Defective Prompt")
    assert report.delta_accuracy_pct < 0
    assert report.recommendation == "REJECT"


def test_ab_eval_runner_full_suite():
    runner = ABEvalRunner()
    fixtures = runner.load_fixtures()
    assert len(fixtures) >= 5

    golden = get_default_golden_candidates()
    # Baseline is golden
    # Candidate has a slight modification or identical
    report = runner.run_ab_benchmark(
        baseline_decisions=golden,
        candidate_decisions=golden,
        experiment_name="Golden vs Golden Baseline",
    )
    assert report.baseline.total_scenarios >= 5
    assert report.baseline.oracle_pass_rate_pct == 100.0
    assert report.candidate.oracle_pass_rate_pct == 100.0
    assert report.delta_accuracy_pct == 0.0
