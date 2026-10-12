import pytest
from analysis.memory.failure_taxonomy import (
    FailureCategory,
    ReasoningFailureRecord,
    FailureClassifier,
    generate_negative_constraints,
    PREVENTATIVE_RULES
)


def test_failure_classifier_from_text():
    assert FailureClassifier.classify_from_text("Caught in a false breakout and bull trap") == FailureCategory.FALSE_BREAKOUT
    assert FailureClassifier.classify_from_text("SL too tight against noise") == FailureCategory.SL_TOO_TIGHT
    assert FailureClassifier.classify_from_text("Premature entry before price pullback completed") == FailureCategory.TIMING_EARLY
    assert FailureClassifier.classify_from_text("Wild volatility spike during CPI release") == FailureCategory.NEWS_SPIKE
    assert FailureClassifier.classify_from_text("Some random comment") == FailureCategory.UNKNOWN_FAILURE


def test_failure_classifier_from_metrics_news_spike():
    metrics = {
        "pnl": -150.0,
        "minutes_to_news": 4.0,  # Within 15 minutes
        "spread_at_entry": 1.2,
        "normal_spread": 1.0,
        "sl_pips": 20.0,
        "atr_pips": 15.0
    }
    assert FailureClassifier.classify_from_metrics(metrics) == FailureCategory.NEWS_SPIKE


def test_failure_classifier_from_metrics_slippage():
    metrics = {
        "pnl": -80.0,
        "minutes_to_news": 120.0,
        "spread_at_entry": 4.5,  # 4.5x normal spread
        "normal_spread": 1.0,
        "sl_pips": 25.0,
        "atr_pips": 20.0
    }
    assert FailureClassifier.classify_from_metrics(metrics) == FailureCategory.EXECUTION_SLIPPAGE


def test_failure_classifier_from_metrics_tight_sl():
    metrics = {
        "pnl": -50.0,
        "minutes_to_news": 180.0,
        "spread_at_entry": 1.0,
        "normal_spread": 1.0,
        "sl_pips": 5.0,   # 5 pips vs 15 pips ATR (< 0.8x ATR)
        "atr_pips": 15.0
    }
    assert FailureClassifier.classify_from_metrics(metrics) == FailureCategory.SL_TOO_TIGHT


def test_generate_negative_constraints():
    failures = [
        FailureCategory.FALSE_BREAKOUT,
        "premature entry before retest",
        ReasoningFailureRecord(symbol="EURUSD", failure_category=FailureCategory.SL_TOO_TIGHT),
        FailureCategory.FALSE_BREAKOUT  # Duplicate should be ignored
    ]
    
    constraints = generate_negative_constraints(failures, symbol="EURUSD", max_constraints=3)
    assert len(constraints) == 3
    assert any("FALSE_BREAKOUT" in c for c in constraints)
    assert any("TIMING_EARLY" in c for c in constraints)
    assert any("SL_TOO_TIGHT" in c for c in constraints)
    assert all("EURUSD" in c for c in constraints)
