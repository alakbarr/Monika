from collections import namedtuple
import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold

TradeStats = namedtuple('TradeStats', ['total_trades', 'winning_trades'])

@pytest.mark.asyncio
async def test_unified_threshold_base_and_regime_cap():
    session = AsyncMock()
    
    mock_vix = MagicMock()
    mock_vix.close = 22.0
    mock_losses = []
    mock_cfg = None
    mock_trade_stats = TradeStats(total_trades=0, winning_trades=0)

    def mock_execute(query):
        res = MagicMock()
        q_str = str(query)
        if 'vix_data' in q_str.lower():
            res.scalar_one_or_none.return_value = mock_vix
        elif 'system_configs' in q_str.lower():
            res.scalar_one_or_none.return_value = mock_cfg
        elif 'paper_trades' in q_str.lower() and 'count' in q_str.lower():
            res.first.return_value = mock_trade_stats
        elif 'paper_trades' in q_str.lower():
            res.scalars.return_value.all.return_value = mock_losses
            res.first.return_value = mock_trade_stats
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
            res.first.return_value = mock_trade_stats
        return res

    session.execute.side_effect = mock_execute
    
    settings = {
        'trading': {
            'auto_execute_min_confluence': 7
        }
    }
    
    threshold, reasoning = await compute_unified_confluence_threshold(
        session, 'EURUSD', settings, stage1_confidence=0.75
    )
    
    assert 5 <= threshold <= 12
    assert 'FINAL THRESHOLD' in reasoning

@pytest.mark.asyncio
async def test_unified_threshold_elevated_vix_over_30():
    session = AsyncMock()
    
    mock_vix = MagicMock()
    mock_vix.close = 32.0  # > 30 triggers +1 penalty
    mock_trade_stats = TradeStats(total_trades=0, winning_trades=0)
    
    def mock_execute(query):
        res = MagicMock()
        q_str = str(query)
        if 'vix_data' in q_str.lower():
            res.scalar_one_or_none.return_value = mock_vix
        elif 'paper_trades' in q_str.lower() and 'count' in q_str.lower():
            res.first.return_value = mock_trade_stats
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
            res.first.return_value = mock_trade_stats
        return res

    session.execute.side_effect = mock_execute
    
    settings = {}
    threshold, reasoning = await compute_unified_confluence_threshold(
        session, 'EURUSD', settings, stage1_confidence=0.80
    )
    
    assert 'elevated_vix(32.0)' in reasoning
    assert '+1' in reasoning


@pytest.mark.asyncio
async def test_unified_threshold_logging_live_vs_backtest(caplog):
    import logging
    from datetime import datetime, timezone

    session = AsyncMock()
    mock_trade_stats = TradeStats(total_trades=0, winning_trades=0)

    def mock_execute(query):
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        res.scalars.return_value.all.return_value = []
        res.first.return_value = mock_trade_stats
        return res

    session.execute.side_effect = mock_execute
    settings = {}

    with caplog.at_level(logging.DEBUG, logger='TradingAgent.UnifiedThreshold'):
        caplog.clear()

        # 1. Live call (default: is_backtest=False, as_of=None) -> should log INFO
        await compute_unified_confluence_threshold(session, 'EURUSD', settings)
        info_records = [r for r in caplog.records if r.levelname == 'INFO' and '[EURUSD] Unified threshold:' in r.message]
        assert len(info_records) == 1

        caplog.clear()

        # 2. Backtest explicit call (is_backtest=True) -> should log DEBUG, NOT INFO
        await compute_unified_confluence_threshold(session, 'EURUSD', settings, is_backtest=True)
        debug_records = [r for r in caplog.records if r.levelname == 'DEBUG' and '[EURUSD] Unified threshold:' in r.message]
        info_records = [r for r in caplog.records if r.levelname == 'INFO' and '[EURUSD] Unified threshold:' in r.message]
        assert len(debug_records) == 1
        assert len(info_records) == 0

        caplog.clear()

        # 3. Point-in-time backtest call (as_of is set) -> should log DEBUG, NOT INFO
        await compute_unified_confluence_threshold(session, 'EURUSD', settings, as_of=datetime(2026, 8, 1, tzinfo=timezone.utc))
        debug_records = [r for r in caplog.records if r.levelname == 'DEBUG' and '[EURUSD] Unified threshold:' in r.message]
        info_records = [r for r in caplog.records if r.levelname == 'INFO' and '[EURUSD] Unified threshold:' in r.message]
        assert len(debug_records) == 1
        assert len(info_records) == 0

