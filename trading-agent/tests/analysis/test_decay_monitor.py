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


@pytest.mark.asyncio
async def test_decay_monitor_suppresses_registry_evaluation():
    from unittest.mock import AsyncMock
    from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
    from analysis.strategies.registry import StrategyRegistry

    class MockDecayingStrategy(EdgeStrategy):
        strategy_id = "test_decay_strat"
        applicable_symbols = {"EURUSD"}

        async def evaluate(self, session, symbol, settings):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="buy",
                valid=True,
                confidence=0.88,
            )

    orig_registry = dict(StrategyRegistry._registry)
    StrategyRegistry._registry = {"test_decay_strat": MockDecayingStrategy}
    monitor = get_strategy_decay_monitor()
    strat_id = "test_decay_strat"
    monitor._health_map.pop(strat_id, None)

    mock_session = AsyncMock()
    mock_session.execute.return_value.scalars.return_value.all.return_value = []

    try:
        # 1. Healthy: evaluate_all yields signal
        signals = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {})
        assert len(signals) == 1
        assert signals[0].strategy_id == strat_id

        # 2. Push strategy to DECAYED state via consecutive losses (3 warnings to MONITORING + 2 to DECAYED)
        for _ in range(8):
            monitor.record_trade_outcome(strat_id, win=False)

        assert monitor.get_health(strat_id).state == DecayState.DECAYED
        assert monitor.is_tradeable(strat_id) is False

        # 3. Decayed: evaluate_all suppresses signal
        signals_suppressed = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {})
        assert len(signals_suppressed) == 0
    finally:
        StrategyRegistry._registry = orig_registry
        monitor._health_map.pop(strat_id, None)


@pytest.mark.asyncio
async def test_paper_tracker_records_decay_outcome():
    from unittest.mock import AsyncMock, MagicMock
    from utils.analytics.paper_tracker import PaperTracker

    monitor = get_strategy_decay_monitor()
    strat_id = "test_paper_alpha"
    monitor._health_map.pop(strat_id, None)

    tracker = PaperTracker(settings={})
    mock_session = AsyncMock()

    mock_analysis = MagicMock()
    mock_analysis.source_strategy_id = strat_id

    mock_trade = MagicMock()
    mock_trade.analysis_id = 999
    mock_trade.pnl_pct = -1.5

    mock_session.get = AsyncMock(return_value=mock_analysis)
    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_analysis

    try:
        await tracker._record_decay_outcome(mock_session, mock_trade)
        health = monitor.get_health(strat_id)
        assert health.consecutive_losses == 1
    finally:
        monitor._health_map.pop(strat_id, None)


def test_decay_monitor_serialization():
    from analysis.strategies.decay_monitor import StrategyDecayMonitor, DecayState

    mon = StrategyDecayMonitor()
    strat = "alpha_serialized"
    # Push to DECAYED
    for _ in range(8):
        mon.record_trade_outcome(strat, win=False)
    
    assert mon.get_health(strat).state == DecayState.DECAYED
    data = mon.to_dict()
    assert strat in data
    assert data[strat]["state"] == "decayed"

    # Restore in new monitor
    mon2 = StrategyDecayMonitor()
    mon2.from_dict(data)
    h2 = mon2.get_health(strat)
    assert h2.state == DecayState.DECAYED
    assert h2.consecutive_losses == 8
    assert mon2.is_tradeable(strat) is False


@pytest.mark.asyncio
async def test_decay_monitor_db_persistence():
    import json
    from unittest.mock import AsyncMock, MagicMock
    from analysis.strategies.decay_monitor import StrategyDecayMonitor, DecayState

    mon = StrategyDecayMonitor()
    strat = "db_alpha"
    for _ in range(8):
        mon.record_trade_outcome(strat, win=False)

    saved_payload = None

    mock_session = AsyncMock()
    mock_cfg = MagicMock()
    
    # Mock upsert capture
    async def mock_upsert(session, key, value, description=None):
        nonlocal saved_payload
        saved_payload = value
        mock_cfg.value = value
        return mock_cfg

    from unittest.mock import patch
    with patch("database.models.SystemConfig.upsert", side_effect=mock_upsert):
        await mon.save_to_db(mock_session)

    assert saved_payload is not None
    data = json.loads(saved_payload)
    assert strat in data
    assert data[strat]["state"] == "decayed"

    # Test load_from_db
    mon_restored = StrategyDecayMonitor()
    mock_row = MagicMock()
    mock_row.value = saved_payload
    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_row

    await mon_restored.load_from_db(mock_session)
    assert mon_restored.get_health(strat).state == DecayState.DECAYED
    assert mon_restored.is_tradeable(strat) is False

