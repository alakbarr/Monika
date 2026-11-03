import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from monika.domain.market.candle_ring_buffer import (
    CandleRingBuffer,
    RingBufferHub,
    CANDLE_DTYPE,
)


def test_candle_ring_buffer_basic_append():
    buf = CandleRingBuffer(capacity=10)
    assert buf.size == 0

    base_time = 1700000000
    for i in range(5):
        buf.append_or_update(
            timestamp=base_time + i * 60,
            open_=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=500.0,
        )

    assert buf.size == 5
    latest = buf.get_latest(3)
    assert len(latest) == 3
    # Check chronological order (oldest to newest)
    assert latest["timestamp"][0] == base_time + 2 * 60
    assert latest["timestamp"][-1] == base_time + 4 * 60
    assert latest["close"][-1] == 102.0 + 4


def test_candle_ring_buffer_in_place_update():
    buf = CandleRingBuffer(capacity=10)
    base_time = 1700000000

    # First tick opens candle
    buf.append_or_update(base_time, 100.0, 101.0, 99.0, 100.5, 10.0)
    assert buf.size == 1

    # Second tick updates the same candle in-place
    buf.append_or_update(base_time, 100.0, 103.0, 98.0, 102.0, 25.0)
    assert buf.size == 1

    latest = buf.get_latest(1)
    assert latest["high"][0] == 103.0
    assert latest["low"][0] == 98.0
    assert latest["close"][0] == 102.0
    assert latest["volume"][0] == 25.0


def test_candle_ring_buffer_circular_wrap():
    cap = 5
    buf = CandleRingBuffer(capacity=cap)
    base_time = 1700000000

    # Append 8 candles to a capacity-5 buffer
    for i in range(8):
        buf.append_or_update(base_time + i * 60, 10.0 + i, 15.0 + i, 5.0 + i, 12.0 + i, 100.0)

    assert buf.size == cap

    # Retrieve all 5
    latest = buf.get_latest(5)
    assert len(latest) == 5
    # Should contain candles index 3, 4, 5, 6, 7
    expected_ts = [base_time + i * 60 for i in range(3, 8)]
    np.testing.assert_array_equal(latest["timestamp"], expected_ts)

    # Retrieve fewer than capacity
    latest_3 = buf.get_latest(3)
    assert len(latest_3) == 3
    assert latest_3["timestamp"][-1] == base_time + 7 * 60


def test_candle_ring_buffer_to_dataframe():
    buf = CandleRingBuffer(capacity=10)
    base_time = 1700000000
    for i in range(4):
        buf.append_or_update(base_time + i * 60, 1.0, 2.0, 0.5, 1.5, 50.0)

    df = buf.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 4
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is not None


def test_ring_buffer_hub_singleton_and_tick():
    RingBufferHub.reset()
    hub = RingBufferHub.get_instance(default_capacity=50)

    # Initially empty
    assert not hub.has_buffer("XAUUSD", "M15")
    assert hub.get_latest_candles("XAUUSD", "M15") == []

    # Seed initial rows
    mock_rows = [
        {
            "timestamp": 1700000000 + i * 900,
            "open": 2000.0 + i,
            "high": 2005.0,
            "low": 1995.0,
            "close": 2002.0,
            "volume": 100,
        }
        for i in range(5)
    ]
    added = hub.update_from_ohlcv_rows("XAUUSD", "M15", mock_rows)
    assert added == 5
    assert hub.has_buffer("XAUUSD", "M15")

    candles = hub.get_latest_candles("XAUUSD", "M15", count=3)
    assert len(candles) == 3
    assert candles[-1]["open"] == 2004.0

    # On tick update
    hub.on_tick("XAUUSD", bid=2010.0, ask=2010.5, last=2010.2)
    updated = hub.get_latest_candles("XAUUSD", "M15", count=1)
    assert len(updated) == 1
    assert updated[0]["close"] == 2010.2

    RingBufferHub.reset()


def test_ring_buffer_performance_benchmark():
    buf = CandleRingBuffer(capacity=1000)
    for i in range(1000):
        buf.append_or_update(1700000000 + i * 60, 100.0, 105.0, 95.0, 102.0, 100.0)

    t0 = time.perf_counter()
    for _ in range(5000):
        _ = buf.get_latest(100)
    elapsed = time.perf_counter() - t0

    # 5,000 retrievals must be well under 0.25 seconds (<50 microseconds each)
    assert elapsed < 0.25, f"RingBuffer retrieval too slow: {elapsed:.4f}s for 5,000 runs"
