import pytest
import math
from unittest.mock import AsyncMock, MagicMock
from utils.analytics.edge_tracker import compute_edge_status, binomial_confidence_interval


def test_binomial_confidence_interval():
    lower, upper = binomial_confidence_interval(55, 100)
    assert lower > 0
    assert upper < 1
    assert lower < upper


@pytest.mark.asyncio
async def test_compute_edge_status_insufficient():
    """Test bahwa status insufficient_data dikembalikan saat < 30 trades."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [MagicMock() for _ in range(10)]
    mock_session.execute.return_value = mock_result
    
    result = await compute_edge_status(mock_session)
    assert result['status'] == 'insufficient_data'
    assert result['trades'] == 10


@pytest.mark.asyncio
async def test_compute_edge_status_positive():
    """Test edge status positif dengan 40 trade (25 wins, 15 losses)."""
    mock_session = AsyncMock()
    records = []
    for _ in range(25):
        m = MagicMock()
        m.exit_reason = 'tp_hit'
        # Tidak ada entry_price/sl/tp → R:R calc gagal → fallback ke 33.3%
        m.entry_price = None
        m.sl = None
        m.tp = None
        records.append(m)
    for _ in range(15):
        m = MagicMock()
        m.exit_reason = 'sl_hit'
        m.entry_price = None
        m.sl = None
        m.tp = None
        records.append(m)
        
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    mock_session.execute.return_value = mock_result
    
    result = await compute_edge_status(mock_session)
    assert result['status'] in ['positive_edge', 'uncertain']  # 62.5% WR dengan breakeven ~33%
    assert result['win_rate'] == 62.5
    assert result['total_trades'] == 40


@pytest.mark.asyncio
async def test_compute_edge_status_dynamic_breakeven_r3():
    """
    Test dynamic breakeven win-rate calculation from empirical R:R data.
    
    If average R:R = 2.0 (reward = 2x risk):
    Breakeven WR = 1 / (1 + 2.0) = 33.33%
    
    If average R:R = 1.0 (reward = 1x risk):
    Breakeven WR = 1 / (1 + 1.0) = 50%
    """
    mock_session = AsyncMock()
    
    records = []
    # 30 trades dengan R:R 1:1 (entry=100, sl=95, tp=105 → R:R=1.0)
    # Breakeven WR harus naik ke 50% (bukan 33.3%)
    for i in range(20):
        m = MagicMock()
        m.exit_reason = 'tp_hit'
        m.entry_price = 100.0
        m.sl = 95.0      # risk = 5
        m.tp = 105.0     # reward = 5 → R:R = 1.0
        records.append(m)
    for i in range(10):
        m = MagicMock()
        m.exit_reason = 'sl_hit'
        m.entry_price = 100.0
        m.sl = 95.0
        m.tp = 105.0
        records.append(m)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    mock_session.execute.return_value = mock_result
    
    result = await compute_edge_status(mock_session)
    # 30 trades: 20 wins (66.7%) vs breakeven ~50% (R:R 1:1)
    # Z-score should be positive, status uncertain or positive_edge
    assert result['total_trades'] == 30
    assert result['win_rate'] == pytest.approx(66.67, abs=0.1)
    # Breakeven WR dinamis ≈ 50%, z-score harus > 0 (WR > breakeven)
    assert result['z_score'] > 0
    # Status harus positif atau uncertain (bukan no_edge)
    assert result['status'] in ['positive_edge', 'uncertain']


@pytest.mark.asyncio
async def test_compute_edge_status_no_edge():
    """Test status no_edge saat WR jauh di bawah breakeven."""
    mock_session = AsyncMock()
    records = []
    # 30 trades: 10 wins (33.3%) — tepat di breakeven default 33.3%
    # Tapi dengan data yg cukup, z-score ≈ 0 → uncertain atau no_edge
    for i in range(10):
        m = MagicMock()
        m.exit_reason = 'tp_hit'
        m.entry_price = None
        m.sl = None
        m.tp = None
        records.append(m)
    for i in range(20):
        m = MagicMock()
        m.exit_reason = 'sl_hit'
        m.entry_price = None
        m.sl = None
        m.tp = None
        records.append(m)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    mock_session.execute.return_value = mock_result
    
    result = await compute_edge_status(mock_session)
    assert result['total_trades'] == 30
    assert result['win_rate'] == pytest.approx(33.33, abs=0.1)
    # z_score ≈ 0 atau negatif → no_edge atau uncertain
    assert result['status'] in ['no_edge', 'uncertain']
