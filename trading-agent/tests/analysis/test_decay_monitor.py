"""
Unit tests for analysis/strategies/decay_monitor.py.
Tests state machine transitions: ACTIVE -> MONITORING -> DECAYED -> DISABLED,
recovery logic, and is_tradeable gating.
"""
import pytest
from analysis.strategies.decay_monitor import (
    StrategyDecayMonitor,
    DecayState,
    get_strategy_decay_monitor,
)


def test_decay_monitor_initial_state():
    monitor = StrategyDecayMonitor()
    health = monitor.get_health("test_strat_1")
    assert health.state == DecayState.ACTIVE
    assert health.warning_count == 0
    assert monitor.is_tradeable("test_strat_1") is True


def test_decay_monitor_consecutive_losses_transition():
    monitor = StrategyDecayMonitor()
    strat = "loss_strat"

    # 3 losses -> no warning yet
    for _ in range(3):
        monitor.record_trade_outcome(strat, win=False)
    assert monitor.get_health(strat).warning_count == 0

    # 4th loss -> triggers 1st warning
    monitor.record_trade_outcome(strat, win=False)
    assert monitor.get_health(strat).warning_count == 1
    assert monitor.get_health(strat).state == DecayState.ACTIVE

    # 5th and 6th losses -> 2nd and 3rd warnings -> transitions to MONITORING
    monitor.record_trade_outcome(strat, win=False)
    monitor.record_trade_outcome(strat, win=False)
    assert monitor.get_health(strat).state == DecayState.MONITORING
    # Still tradeable under MONITORING
    assert monitor.is_tradeable(strat) is True

    # 2 more warnings in MONITORING -> transitions to DECAYED
    monitor.record_trade_outcome(strat, win=False)
    monitor.record_trade_outcome(strat, win=False)
    assert monitor.get_health(strat).state == DecayState.DECAYED
    # NOT tradeable under DECAYED
    assert monitor.is_tradeable(strat) is False


def test_decay_monitor_evaluate_window():
    monitor = StrategyDecayMonitor()
    strat = "winrate_strat"

    # 10 trades with only 2 wins (20% win rate, below 35% absolute floor)
    trades = [{"pnl": -10.0}] * 8 + [{"pnl": 10.0}] * 2

    # 3 evaluations -> 3 warnings -> transitions to MONITORING
    for _ in range(3):
        monitor.evaluate(strat, trades, baseline_win_rate=0.55)

    assert monitor.get_health(strat).state == DecayState.MONITORING
    assert monitor.get_health(strat).rolling_win_rate == 0.2


def test_decay_monitor_recovery():
    monitor = StrategyDecayMonitor()
    strat = "recovery_strat"

    # Push to MONITORING
    for _ in range(6):
        monitor.record_trade_outcome(strat, win=False)
    assert monitor.get_health(strat).state == DecayState.MONITORING

    # Healthy trades bring warning count down
    for _ in range(5):
        monitor.record_trade_outcome(strat, win=True)

    # Evaluate with healthy 70% win rate
    good_trades = [{"pnl": 10.0}] * 7 + [{"pnl": -10.0}] * 3
    monitor.evaluate(strat, good_trades, baseline_win_rate=0.55)

    assert monitor.get_health(strat).state == DecayState.ACTIVE
    assert monitor.is_tradeable(strat) is True
