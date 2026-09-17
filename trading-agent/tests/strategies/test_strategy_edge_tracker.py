import pytest
from unittest.mock import AsyncMock, MagicMock
from utils.analytics.strategy_edge_tracker import compute_strategy_pair_stats, apply_disable_flags

@pytest.mark.asyncio
async def test_compute_strategy_pair_stats():
    session = AsyncMock()
    
    class MockAnalysis:
        def __init__(self, strat, sym):
            self.source_strategy_id = strat
            self.symbol = sym

    class MockRecord:
        def __init__(self, pnl):
            self.pnl_pct = pnl
            
    mock_result = MagicMock()
    # 2 wins (1.5, 2.0) and 1 loss (-1.0)
    mock_result.all.return_value = [
        (MockRecord(1.5), MockAnalysis('gap_fade', 'EURUSD')),
        (MockRecord(2.0), MockAnalysis('gap_fade', 'EURUSD')),
        (MockRecord(-1.0), MockAnalysis('gap_fade', 'EURUSD'))
    ]
    session.execute.return_value = mock_result
    
    stats = await compute_strategy_pair_stats(session, {})
    
    assert 'gap_fade_EURUSD' in stats
    res = stats['gap_fade_EURUSD']
    assert res['strategy_id'] == 'gap_fade'
    assert res['symbol'] == 'EURUSD'
    assert res['trades'] == 3
    assert res['win_rate_pct'] == 66.7
    assert res['profit_factor'] == 3.5

@pytest.mark.asyncio
async def test_apply_disable_flags():
    session = AsyncMock()
    
    class MockAnalysis:
        def __init__(self, strat, sym):
            self.source_strategy_id = strat
            self.symbol = sym

    class MockRecord:
        def __init__(self, pnl):
            self.pnl_pct = pnl

    mock_result = MagicMock()
    # 20 trades, profit factor < 1.0 (win=0.5, loss=1.0)
    rows = []
    for _ in range(10):
        rows.append((MockRecord(0.5), MockAnalysis('gap_fade', 'EURUSD')))
    for _ in range(10):
        rows.append((MockRecord(-1.0), MockAnalysis('gap_fade', 'EURUSD')))
        
    mock_result.all.return_value = rows
    
    # Second execute call for select(SystemConfig)
    mock_cfg_result = MagicMock()
    mock_cfg_result.scalar_one_or_none.return_value = None
    
    session.execute.side_effect = [mock_result, mock_cfg_result]
    
    settings = {}
    disabled = await apply_disable_flags(session, settings)
    
    assert 'gap_fade_EURUSD' in disabled
    assert session.add.called
    assert session.commit.called
