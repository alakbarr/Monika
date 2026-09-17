# ==============================================================================
# File: tests/execution/test_mt5_chunked_fetch.py
# ==============================================================================

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
import numpy as np
import pandas as pd
import pytest

from execution.mt5_client import MT5Client


def _make_dummy_rates(start_ts: int, count: int):
    dtype = [
        ('time', '<i8'),
        ('open', '<f8'),
        ('high', '<f8'),
        ('low', '<f8'),
        ('close', '<f8'),
        ('tick_volume', '<i8'),
        ('spread', '<i4'),
        ('real_volume', '<i8')
    ]
    arr = np.zeros(count, dtype=dtype)
    for i in range(count):
        arr[i] = (start_ts + i * 3600, 1.0800 + i * 0.0001, 1.0850, 1.0790, 1.0820, 100, 10, 0)
    return arr


@pytest.mark.asyncio
async def test_get_ohlcv_small_count_single_call():
    client = MT5Client()
    client.is_connected = AsyncMock(return_value=True)
    dummy = _make_dummy_rates(1700000000, 100)

    with patch.object(client, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = dummy
        df = await client.get_ohlcv("EURUSD", "H1", count=100, chunk_size=300)

    assert df is not None
    assert len(df) == 100
    assert mock_run.call_count == 1
    assert "close" in df.columns
    assert "volume" in df.columns


@pytest.mark.asyncio
async def test_get_ohlcv_large_count_chunked():
    client = MT5Client()
    client.is_connected = AsyncMock(return_value=True)

    dummy1 = _make_dummy_rates(1700000000, 300)
    dummy2 = _make_dummy_rates(1700000000 + 300 * 3600, 200)

    with patch.object(client, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [dummy1, dummy2]
        df = await client.get_ohlcv("EURUSD", "H1", count=500, chunk_size=300)

    assert df is not None
    assert len(df) == 500
    assert mock_run.call_count == 2
    assert df.iloc[0]["close"] is not None


@pytest.mark.asyncio
async def test_copy_rates_range_chunked():
    client = MT5Client()
    client.is_connected = AsyncMock(return_value=True)

    d_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d_to = datetime(2026, 1, 20, tzinfo=timezone.utc)  # 19 days -> 3 chunks (7 + 7 + 5)

    dummy1 = _make_dummy_rates(1700000000, 50)
    dummy2 = _make_dummy_rates(1700000000 + 50 * 3600, 50)
    dummy3 = _make_dummy_rates(1700000000 + 100 * 3600, 30)

    with patch.object(client, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [dummy1, dummy2, dummy3]
        df = await client.copy_rates_range("EURUSD", "H1", d_from, d_to, chunk_days=7)

    assert df is not None
    assert len(df) == 130
    assert mock_run.call_count == 3
