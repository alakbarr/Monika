import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock
from utils.protocol.enhanced_cds import (
    compute_spatial_cds,
    compute_task_cds,
    get_cds_thresholds,
    get_signal_threshold
)

@pytest.mark.asyncio
async def test_compute_spatial_cds_aligned_strong_bullish():
    """Test that strong_bullish with upward price move is correctly normalized and yields 0.0 CDS."""
    session = AsyncMock()
    
    # 20 H4 bars with upward move: first_close=1.2000, last_close=1.2100 (+0.83% move)
    bars = []
    for i in range(20):
        bar = MagicMock()
        bar.close = 1.2000 + (i * 0.0005)
        bar.timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=(20 - i) * 4)
        bars.append(bar)
    
    mock_result = MagicMock()
    # reversed in implementation: bars ordered by timestamp desc, so first returned is latest
    mock_result.scalars.return_value.all.return_value = list(reversed(bars))
    session.execute.return_value = mock_result
    
    brief_currency_bias = {"GBP": "strong_bullish", "USD": "neutral"}
    cds = await compute_spatial_cds(session, "GBPUSD", brief_currency_bias)
    
    # Since GBP is strong_bullish (normalized to bullish) and price moved up (bullish), CDS must be 0.0
    assert cds == 0.0

@pytest.mark.asyncio
async def test_compute_spatial_cds_divergent_strong_bullish():
    """Test that strong_bullish with downward price move yields divergence (> 0.0 CDS)."""
    session = AsyncMock()
    
    # 20 H4 bars with downward move: first_close=1.2100, last_close=1.2000 (-0.83% move)
    bars = []
    for i in range(20):
        bar = MagicMock()
        bar.close = 1.2100 - (i * 0.0005)
        bar.timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=(20 - i) * 4)
        bars.append(bar)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = list(reversed(bars))
    session.execute.return_value = mock_result
    
    brief_currency_bias = {"GBP": "strong_bullish", "USD": "neutral"}
    cds = await compute_spatial_cds(session, "GBPUSD", brief_currency_bias)
    
    # Since GBP is strong_bullish (bullish) but price moved down (bearish), CDS must be > 0.0
    assert cds > 0.0

@pytest.mark.asyncio
async def test_compute_task_cds():
    session = AsyncMock()
    
    # Test with < 3 analyses
    mock_res_empty = MagicMock()
    mock_res_empty.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res_empty
    task_cds = await compute_task_cds(session, "GBPUSD", "buy")
    assert task_cds == 0.0

    # Test with 3 consecutive waits (decaying penalty starts at 0.25)
    mock_analyses_3 = [
        MagicMock(decision='wait'),
        MagicMock(decision='wait'),
        MagicMock(decision='wait'),
    ]
    mock_res_3 = MagicMock()
    mock_res_3.scalars.return_value.all.return_value = mock_analyses_3
    session.execute.return_value = mock_res_3
    task_cds_3 = await compute_task_cds(session, "GBPUSD", "buy")
    assert task_cds_3 == 0.25

    # Test with 5 consecutive waits (decaying: 0.25 - 2*0.05 = 0.15)
    mock_analyses_5 = [
        MagicMock(decision='wait'),
        MagicMock(decision='wait'),
        MagicMock(decision='wait'),
        MagicMock(decision='wait'),
        MagicMock(decision='wait'),
    ]
    mock_res_5 = MagicMock()
    mock_res_5.scalars.return_value.all.return_value = mock_analyses_5
    session.execute.return_value = mock_res_5
    task_cds_5 = await compute_task_cds(session, "GBPUSD", "buy")
    assert round(task_cds_5, 2) == 0.15

def test_get_cds_thresholds():
    thresholds = get_cds_thresholds()
    assert thresholds['warning'] == 0.35
    assert thresholds['sync_trigger'] == 0.50
    assert thresholds['block_buysell'] == 0.65
    assert thresholds['abort_all'] == 0.75

def test_get_signal_threshold():
    assert get_signal_threshold("GBPUSD") == 0.005
    assert get_signal_threshold("BTCUSD") == 0.015
    assert get_signal_threshold("XAUUSD") == 0.008
