"""
Unit & Regression Tests for Remediation Phase 0 & Phase 1.
"""
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock
from database.models import BacktestRun, BacktestTrade, PaperTradeRecord, AssetAnalysis
from backtest.report_generator import ReportGenerator
from backtest.outcome_evaluator import OutcomeEvaluator
from utils.calibration.confidence_calibrator import compute_confidence_calibration, apply_calibration_correction
from analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema
from risk.position_sizing import PositionSizer, InstrumentSpec


def test_sharpe_ratio_annualization_sqrt_252():
    """Verify that ReportGenerator computes Sharpe ratio scaled by sqrt(252)."""
    run = BacktestRun(initial_equity=10000.0)
    # Generate 5 returns: 10000 -> 10100 -> 10200 -> 10300 -> 10400 -> 10500
    equity_curve = [10000.0, 10100.0, 10200.0, 10300.0, 10400.0, 10500.0]
    trades = [
        BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=1.0),
        BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=1.0),
        BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=1.0),
        BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=1.0),
        BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=1.0),
    ]
    gen = ReportGenerator(run=run, trades=trades, equity_curve=equity_curve)
    gen.calculate_metrics()

    returns = np.diff(equity_curve) / equity_curve[:-1]
    expected_sharpe = float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252))
    assert abs(run.sharpe_ratio - round(expected_sharpe, 2)) < 1e-4
    assert run.sharpe_ratio > 0.0


def test_outcome_evaluator_pip_calculation():
    """Verify outcome evaluator pip calculation uses dynamic pip sizes for Gold and Crypto."""
    evaluator = OutcomeEvaluator()
    from datetime import datetime, timezone
    
    # Gold test (pip_size = 0.01 or 0.1 depending on spec, here 0.01 for 100 multiplier)
    gold_trade = BacktestTrade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0
    )
    outcome_gold = evaluator._calculate_outcome(
        gold_trade,
        exit_time=datetime.now(timezone.utc),
        exit_price=2010.0,
        reason="tp_hit"
    )
    # Price difference = $10.0. With pip_size=0.01 -> 1000 pips
    assert outcome_gold["pnl_pips"] == 1000.0
    assert outcome_gold["pnl_pct"] == 0.5

    # BTC test (pip_size = 1.0)
    btc_trade = BacktestTrade(
        symbol="BTCUSD",
        direction="sell",
        entry_price=60000.0,
        stop_loss=61000.0,
        take_profit=58000.0
    )
    outcome_btc = evaluator._calculate_outcome(
        btc_trade,
        exit_time=datetime.now(timezone.utc),
        exit_price=59000.0,
        reason="tp_hit"
    )
    # Price difference = $1000 profit. With pip_size=1.0 -> 1000 pips
    assert outcome_btc["pnl_pips"] == 1000.0


def test_pydantic_confidence_fail_fast_without_default():
    """Verify confidence validator fails when invalid string/None is passed without 0.8 fallback."""
    with pytest.raises(ValueError):
        SubmitFundamentalBriefSchema.validate_confidence("invalid_non_numeric_text")

    # Valid float string should pass
    val = SubmitFundamentalBriefSchema.validate_confidence("0.75")
    assert val == 0.75

    # Percentage string should be scaled
    val_pct = SubmitFundamentalBriefSchema.validate_confidence("85")
    assert val_pct == 0.85


@pytest.mark.asyncio
async def test_confidence_calibrator_ece_and_guard():
    """Verify ECE / Brier score computation and sample guard N>=60."""
    mock_session = AsyncMock()

    # Case 1: < 20 records -> insufficient_data
    mock_result_insufficient = MagicMock()
    mock_result_insufficient.all.return_value = []
    mock_session.execute.return_value = mock_result_insufficient
    res = await compute_confidence_calibration(mock_session)
    assert res["status"] == "insufficient_data"

    # Case 2: 25 records with mixed outcomes -> check ECE and Brier calculation
    mock_records = []
    for i in range(25):
        trade = PaperTradeRecord(exit_reason="tp_hit" if i % 2 == 0 else "sl_hit")
        analysis = AssetAnalysis(confidence=0.75 if i % 2 == 0 else 0.65)
        mock_records.append((trade, analysis))
    
    mock_result_ok = MagicMock()
    mock_result_ok.all.return_value = mock_records
    mock_session.execute.return_value = mock_result_ok

    res_ok = await compute_confidence_calibration(mock_session)
    assert "ece" in res_ok
    assert "brier_score" in res_ok
    assert res_ok["total_analyzed"] == 25
    assert res_ok["brier_score"] > 0.0

    # Test auto-correction guard (should not modify DB because N=25 < 60)
    await apply_calibration_correction(mock_session, {"trading": {"auto_execute_min_confidence": 0.6}})
    # No commit called because N < 60
    assert mock_session.commit.await_count == 0


def test_position_sizing_dynamic_risk_cap_and_unknown_symbol():
    """Verify dynamic max_risk_amount_usd cap and rejection of unlisted symbols when MT5 offline."""
    custom_settings = {
        "trading": {
            "risk": {
                "max_risk_amount_usd": 250.0  # Custom strict cap
            }
        }
    }
    sizer = PositionSizer(mt5_client=None, settings=custom_settings)

    # 1. Unlisted symbol without MT5 info -> must be rejected safely
    res_unknown = sizer.calculate(
        symbol="UNKNOWN_COIN_XYZ",
        direction="buy",
        entry_price=10.0,
        stop_loss=9.0,
        take_profit=11.0,
        account_equity=10000.0,
        risk_percent_override=1.0
    )
    assert res_unknown.is_valid is False
    assert any("Instrument specifications unavailable" in r for r in res_unknown.rejection_reasons)

    # 2. Risk exceeding $250 custom limit -> rejected with custom limit error
    res_large_risk = sizer.calculate(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0900,  # 100 pips
        take_profit=1.1200,
        account_equity=50000.0,
        risk_percent_override=2.0  # $1000 risk > $250 cap
    )
    assert res_large_risk.is_valid is False
    assert any("exceeds configured risk limit of $250.00" in r for r in res_large_risk.rejection_reasons)
