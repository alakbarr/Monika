# ==============================================================================
# File: tests/evals/test_eval_reliability.py
# ==============================================================================

"""Regression tests for eval fail-closed grounding and abstention-aware Brier scoring."""

from monika.application.evals.eval_metrics import (
    DecisionEvaluation,
    aggregate_eval_metrics,
    compute_brier_score,
)
from monika.application.evals.eval_runner import ABEvalRunner


def _decision(decision: str, *, valid: bool, confidence: float | None) -> DecisionEvaluation:
    return DecisionEvaluation(
        scenario_id="s",
        symbol="EURUSD",
        decision=decision,
        is_valid_direction=valid,
        confluence_score=confidence,
        oracle_passed=True,
    )


def test_brier_excludes_abstentions_and_reports_coverage():
    decisions = [
        _decision("BUY", valid=True, confidence=100.0),
        _decision("WAIT", valid=True, confidence=0.0),
    ]

    assert compute_brier_score(decisions) == 0.0

    agg = aggregate_eval_metrics(decisions)
    assert agg.brier_scored_count == 1
    assert agg.abstention_count == 1
    assert agg.brier_score == 0.0


def test_brier_all_abstentions_is_explicitly_unscored():
    decisions = [_decision("WAIT", valid=True, confidence=0.0)]

    agg = aggregate_eval_metrics(decisions)
    assert agg.brier_scored_count == 0
    assert agg.abstention_count == 1


def test_eval_grounding_fails_closed_when_validator_raises(monkeypatch):
    from monika.application.analysis.validators.in_harness_grounding import InHarnessGroundingValidator

    def _boom(cls, **kwargs):
        raise RuntimeError("validator unavailable")

    monkeypatch.setattr(InHarnessGroundingValidator, "verify_grounding", classmethod(_boom))

    runner = ABEvalRunner()
    fixture = runner.load_fixtures()[0]
    evaluation = runner.evaluate_single_decision(fixture, {"decision": "WAIT"})

    assert evaluation.grounding_passed is False
    assert any("grounding" in error.lower() for error in evaluation.grounding_errors)
