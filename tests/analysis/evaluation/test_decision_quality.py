"""
Unit tests for DecisionQualityEvaluator, WAIT-regret calculation, and Brier calibration.
Verifies Phase 5 requirements of the Monika Profitability Remediation Plan.
"""

from datetime import datetime, timezone
import pandas as pd
import pytest

from monika.application.analysis.evaluation.decision_quality import (
    DecisionQualityEvaluator,
    EvaluationOutcome,
    QualityMetrics,
)


def _make_sample_df(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    records = []
    for i, (o, h, l, c) in enumerate(bars):
        records.append(
            {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "timestamp": datetime(2026, 10, 20, i % 24, 0, tzinfo=timezone.utc),
            }
        )
    return pd.DataFrame(records)


def test_actionable_buy_win():
    evaluator = DecisionQualityEvaluator(horizon_bars=10)
    # Price rises from 100 to 106 without dropping below 98
    bars = [
        (100.0, 101.5, 99.5, 101.0),
        (101.0, 103.0, 100.5, 102.5),
        (102.5, 106.5, 102.0, 106.0),
    ]
    df = _make_sample_df(bars)

    outcome = evaluator.evaluate_decision(
        symbol="EURUSD",
        decision="buy",
        decision_time=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        confidence=0.85,
        forward_bars=df,
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=105.0,
        atr=2.0,
    )
    assert outcome.win is True
    assert outcome.loss is False
    assert outcome.actual_outcome == 1.0
    assert outcome.r_multiple == 2.5
    assert abs(outcome.brier_score - (0.85 - 1.0) ** 2) < 1e-4


def test_actionable_buy_loss():
    evaluator = DecisionQualityEvaluator(horizon_bars=10)
    # Price drops below stop loss 98.0
    bars = [
        (100.0, 100.5, 97.5, 98.0),
    ]
    df = _make_sample_df(bars)

    outcome = evaluator.evaluate_decision(
        symbol="EURUSD",
        decision="buy",
        decision_time=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        confidence=0.75,
        forward_bars=df,
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=105.0,
        atr=2.0,
    )
    assert outcome.win is False
    assert outcome.loss is True
    assert outcome.actual_outcome == 0.0
    assert outcome.r_multiple == -1.0
    assert abs(outcome.brier_score - (0.75 - 0.0) ** 2) < 1e-4


def test_actionable_sell_win():
    evaluator = DecisionQualityEvaluator(horizon_bars=10)
    # Price falls from 100 to 94 without rising to 103
    bars = [
        (100.0, 101.0, 97.0, 97.5),
        (97.5, 98.0, 93.5, 94.0),
    ]
    df = _make_sample_df(bars)

    outcome = evaluator.evaluate_decision(
        symbol="EURUSD",
        decision="sell",
        decision_time=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        confidence=0.80,
        forward_bars=df,
        entry_price=100.0,
        stop_loss=103.0,
        take_profit=95.0,
        atr=2.0,
    )
    assert outcome.win is True
    assert outcome.loss is False
    assert outcome.actual_outcome == 1.0


def test_wait_capital_preserved():
    evaluator = DecisionQualityEvaluator(horizon_bars=5, atr_regret_multiple=1.5)
    # Market chops between 99.0 and 101.0 (ATR is 2.0, so 1.5x ATR = 3.0 required for breakout)
    bars = [
        (100.0, 100.8, 99.2, 100.2),
        (100.2, 101.1, 99.0, 99.8),
        (99.8, 100.5, 99.4, 100.0),
    ]
    df = _make_sample_df(bars)

    outcome = evaluator.evaluate_decision(
        symbol="EURUSD",
        decision="wait",
        decision_time=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        confidence=0.90,
        forward_bars=df,
        entry_price=100.0,
        atr=2.0,
    )
    assert outcome.is_wait is True
    assert outcome.capital_preserved is True
    assert outcome.missed_opportunity is False
    assert outcome.actual_outcome == 1.0


def test_wait_missed_opportunity():
    evaluator = DecisionQualityEvaluator(horizon_bars=5, atr_regret_multiple=1.5)
    # Market trends cleanly upward by 4.0 points (2.0x ATR) with almost no pullback
    bars = [
        (100.0, 101.5, 99.8, 101.2),
        (101.2, 103.0, 100.9, 102.8),
        (102.8, 104.5, 102.5, 104.0),
    ]
    df = _make_sample_df(bars)

    outcome = evaluator.evaluate_decision(
        symbol="EURUSD",
        decision="wait",
        decision_time=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        confidence=0.85,
        forward_bars=df,
        entry_price=100.0,
        atr=2.0,
    )
    assert outcome.is_wait is True
    assert outcome.capital_preserved is False
    assert outcome.missed_opportunity is True
    assert outcome.actual_outcome == 0.0


def test_calculate_aggregate_metrics():
    evaluator = DecisionQualityEvaluator()
    outcomes = [
        EvaluationOutcome(
            symbol="EURUSD",
            decision="buy",
            decision_time=datetime.now(timezone.utc),
            confidence=0.8,
            actual_outcome=1.0,
            brier_score=0.04,
            is_actionable=True,
            is_wait=False,
            win=True,
            r_multiple=2.0,
        ),
        EvaluationOutcome(
            symbol="EURUSD",
            decision="sell",
            decision_time=datetime.now(timezone.utc),
            confidence=0.7,
            actual_outcome=0.0,
            brier_score=0.49,
            is_actionable=True,
            is_wait=False,
            loss=True,
            r_multiple=-1.0,
        ),
        EvaluationOutcome(
            symbol="GBPUSD",
            decision="wait",
            decision_time=datetime.now(timezone.utc),
            confidence=0.9,
            actual_outcome=1.0,
            brier_score=0.01,
            is_actionable=False,
            is_wait=True,
            capital_preserved=True,
        ),
    ]
    metrics = evaluator.calculate_aggregate_metrics(outcomes)
    assert metrics.total_decisions == 3
    assert metrics.actionable_count == 2
    assert metrics.wait_count == 1
    assert metrics.win_count == 1
    assert metrics.loss_count == 1
    assert metrics.win_rate == 0.50
    assert metrics.profit_factor == 2.0  # 2.0 / 1.0
    assert metrics.wait_preservation_rate == 1.0
    assert metrics.wait_regret_rate == 0.0
