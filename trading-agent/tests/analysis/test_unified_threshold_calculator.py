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
