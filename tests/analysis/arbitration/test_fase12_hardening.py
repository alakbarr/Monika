import math
import pytest
from datetime import datetime, timezone, UTC
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
from monika.application.analysis.debate.deterministic_risk import (
    analyze_risk_aggressive,
    analyze_risk_neutral,
)
from monika.application.analysis.evaluation.decision_quality import DecisionQualityEvaluator
from monika.application.analysis.strategies.base_strategy import EdgeSignal
from monika.application.analysis.strategies.decay_monitor import StrategyDecayMonitor
from monika.core.calibration.confidence_calibrator import fit_platt_scaling
from monika.core.calibration.cot_thresholds import get_cot_extreme_thresholds, cot_extreme_score
from monika.infrastructure.graph.checkpointers.sqlite_checkpointer import SqliteCheckpointSaver
import tempfile
import os


@pytest.fixture(autouse=True)
def _reset_decay():
    StrategyDecayMonitor.reset()
    yield
    StrategyDecayMonitor.reset()


@pytest.mark.asyncio
async def test_arbitrator_incubating_conflict_suppression():
    """FR-3.5: If quant strategy is still incubating and conflicts with LLM, force avoid."""
    arb = SignalArbitrator()
    mock_session = AsyncMock()
    sig = EdgeSignal(
        strategy_id="incubating_test_strat",
        symbol="EURUSD",
        direction="sell",
        valid=True,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.1050,
        take_profit=1.0900,
    )
    # LLM says buy, quant says sell, quant is NOT live-ready (incubating)
    res = await arb.arbitrate(
        mock_session,
        symbol="EURUSD",
        llm_decision={"decision": "buy", "confidence": 0.70},
        quant_signal=sig,
        entry_price=1.1000,
        sl_price=1.0950,
        tp_price=1.1100,
    )
    assert res.decision == "avoid"
    assert res.selected_source == "conflict_suppression" or res.meta.get("incubation_conflict_suppression") is True
    assert res.risk_multiplier == 0.0


@pytest.mark.asyncio
async def test_arbitrator_missing_or_zero_sl_fails_closed():
    """Zero or negative stop loss must fail closed to avoid."""
    arb = SignalArbitrator()
    mock_session = AsyncMock()
    res = await arb.arbitrate(
        mock_session,
        symbol="EURUSD",
        llm_decision={"decision": "buy", "confidence": 0.80},
        entry_price=1.1000,
        sl_price=0.0,  # Missing/zero SL
        tp_price=1.1100,
    )
    assert res.decision == "avoid"
    assert res.risk_multiplier == 0.0
    assert "Stop Loss" in res.reasoning


@pytest.mark.asyncio
async def test_arbitrator_nan_confidence_fails_closed():
    """NaN confidence input must be sanitized and rejected fail-closed."""
    arb = SignalArbitrator()
    mock_session = AsyncMock()
    res = await arb.arbitrate(
        mock_session,
        symbol="EURUSD",
        llm_decision={"decision": "buy", "confidence": float("nan")},
        entry_price=1.1000,
        sl_price=1.0950,
        tp_price=1.1100,
    )
    assert res.decision == "avoid"
    assert res.risk_multiplier == 0.0


@pytest.mark.asyncio
async def test_arbitrator_global_exception_fails_closed():
    """Any unexpected exception in arbitrator must fail closed with avoid."""
    arb = SignalArbitrator()
    mock_session = AsyncMock()
    with patch.object(arb, "_do_arbitrate", side_effect=RuntimeError("Simulated arbitrator crash")):
        res = await arb.arbitrate(
            mock_session,
            symbol="EURUSD",
            llm_decision={"decision": "buy", "confidence": 0.80},
        )
        assert res.decision == "avoid"
        assert res.risk_multiplier == 0.0
        assert res.selected_source == "fail_closed_exception"


def test_deterministic_risk_vetoes_on_none_rr():
    """Deterministic risk analysis must veto if rr_ratio is None."""
    ctx = {
        "symbol": "EURUSD",
        "market_regime": "ranging",
        "actual_risk_state": {
            "daily_pnl_pct": 0.0,
            "open_positions": 1,
            "portfolio_heat_pct": 1.0,
        },
        "confluence_score": 7,
        "sl_beyond_structure": True,
        "rr_ratio": None,
    }
    agg = analyze_risk_aggressive(ctx)
    assert agg["veto_trade"] is True
    assert "None" in agg["risk_profile_assessment"] or "Fail-Closed" in agg["risk_profile_assessment"]

    neu = analyze_risk_neutral(ctx)
    assert neu["veto_trade"] is True
    assert "None" in neu["risk_profile_assessment"] or "Fail-Closed" in neu["risk_profile_assessment"]


def test_decision_quality_zero_atr_division_guarded():
    """_evaluate_wait_regret with atr=0.0 must not raise ZeroDivisionError."""
    import pandas as pd

    evaluator = DecisionQualityEvaluator()
    horizon_df = pd.DataFrame(
        [
            {"open": 1.1000, "high": 1.1050, "low": 1.0990, "close": 1.1040},
            {"open": 1.1040, "high": 1.1060, "low": 1.1030, "close": 1.1055},
        ]
    )
    outcome = evaluator._evaluate_wait_regret(
        symbol="EURUSD",
        decision="wait",
        decision_time=datetime.now(UTC),
        confidence=0.75,
        horizon_df=horizon_df,
        entry_price=1.1000,
        atr=0.0,
    )
    assert outcome.symbol == "EURUSD"
    assert outcome.is_wait is True


def test_confidence_calibrator_platt_stability():
    """fit_platt_scaling must be stable on small samples and zero variance."""
    # N < 5
    a, b = fit_platt_scaling([0.7, 0.8], [1, 0])
    assert (a, b) == (1.0, 0.0)

    # Zero variance in confidences
    a, b = fit_platt_scaling([0.8, 0.8, 0.8, 0.8, 0.8, 0.8], [1, 1, 0, 1, 0, 1])
    assert (a, b) == (1.0, 0.0)


def test_cot_thresholds_filters_none_and_nan():
    """get_cot_extreme_thresholds must gracefully ignore None, NaN, and string elements."""
    dirty_hist = [80.0, None, 82.0, float("nan"), 75.0, None, 85.0, 88.0, 78.0, 81.0, 79.0, 83.0, 84.0]
    thresholds = get_cot_extreme_thresholds("EURUSD", dirty_hist)
    assert "extreme_long" in thresholds
    assert "extreme_short" in thresholds
    assert thresholds["extreme_long"] > thresholds["extreme_short"]

    # Score with invalid current_percentile returns 0
    assert cot_extreme_score("EURUSD", None) == 0
    assert cot_extreme_score("EURUSD", float("nan")) == 0


def test_sqlite_checkpointer_disk_pruning():
    """SqliteCheckpointSaver.prune_disk_checkpoints must prune safely."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_checkpoints.db")
        saver = SqliteCheckpointSaver(db_path=db_path)
        deleted = saver.prune_disk_checkpoints(max_threads=10, retention_days=1)
        assert deleted == 0
