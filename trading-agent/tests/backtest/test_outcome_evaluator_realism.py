"""
Unit Tests for OutcomeEvaluator Realistic Friction and Dollar PnL.
"""
import pytest
from datetime import datetime, timezone, timedelta
from database.models import BacktestTrade
from backtest.outcome_evaluator import OutcomeEvaluator


def test_outcome_evaluator_gold_friction_and_dollar_pnl():
    """Verify Gold (XAUUSD) applies realistic spread/slippage and calculates accurate dollar PnL."""
    evaluator = OutcomeEvaluator()
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    
    trade = BacktestTrade(
        symbol="XAUUSD",
        direction="buy",
        entry_time=start,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
    )
    trade.executed_lots = 0.5  # 0.5 lot = 50 oz

    # Simulating TP exit at 2020.0
    # Price move = +20.0
    # Gold friction = 30.0 spread + 10.0 slippage = 40.0 pips ($0.40)
    # Gross USD = 0.5 * 100 * 20.0 = $1000
    # Friction USD = 0.5 * 100 * 0.40 = $20.00
    # Net USD = $980.00
    outcome = evaluator._calculate_outcome(trade, start + timedelta(hours=4), 2020.0, "tp_hit", apply_costs=True)

    assert outcome["exit_reason"] == "tp_hit"
    assert outcome["pnl_pips"] > 0
    assert outcome["pnl_usd"] == 980.00
    assert outcome["friction_pips"] == 40.0


def test_outcome_evaluator_btc_friction_and_dollar_pnl():
    """Verify Bitcoin (BTCUSD) applies realistic crypto spread/slippage."""
    evaluator = OutcomeEvaluator()
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    
    trade = BacktestTrade(
        symbol="BTCUSD",
        direction="buy",
        entry_time=start,
        entry_price=58000.0,
        stop_loss=57000.0,
        take_profit=60000.0,
    )
    trade.executed_lots = 0.2  # 0.2 BTC

    # Simulating TP exit at 60000.0 (Buy trade, price gained 2000)
    # BTC friction = 20.0 spread + 10.0 slippage = 30.0 pips ($30)
    # Gross USD = 0.2 * 1 * 2000 = $400
    # Friction USD = 0.2 * 1 * 30 = $6.00
    # Net USD = $394.00
    outcome = evaluator._calculate_outcome(trade, start + timedelta(hours=6), 60000.0, "tp_hit", apply_costs=True)

    assert outcome["exit_reason"] == "tp_hit"
    assert outcome["pnl_usd"] == 394.00
    assert outcome["friction_pips"] == 30.0


def test_outcome_evaluator_latency_and_commission_fee_model():
    """Verify that configured latency and commission fee models correctly deduct costs."""
    evaluator = OutcomeEvaluator(latency_ms=100.0, commission_per_lot_usd=7.0)
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    trade = BacktestTrade(
        symbol="EURUSD",
        direction="buy",
        entry_time=start,
        entry_price=1.0800,
        stop_loss=1.0750,
        take_profit=1.0900,
    )
    trade.executed_lots = 1.0  # 1 standard lot

    outcome = evaluator._calculate_outcome(trade, start + timedelta(hours=2), 1.0900, "tp_hit", apply_costs=True)
    assert outcome["exit_reason"] == "tp_hit"
    assert outcome["latency_ms"] == 100.0
    assert outcome["commission_usd"] == 7.00
    # Gross PnL = 1.0 * 100 pips * $10 = $1000
    # Net USD should be less than $1000 due to spread, slippage, latency, and commission
    assert outcome["pnl_usd"] < 1000.0
    assert outcome["friction_usd"] > 7.0

