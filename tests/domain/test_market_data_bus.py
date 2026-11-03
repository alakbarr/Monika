"""
Unit tests for MarketDataBus (in-memory zero-copy market engine).
"""

from datetime import datetime, timezone

from monika.domain.market.candle_ring_buffer import RingBufferHub
from monika.domain.market.market_data_bus import MarketDataBus


def test_market_data_bus_singleton_and_reset() -> None:
    bus1 = MarketDataBus.get_instance()
    bus2 = MarketDataBus.get_instance()
    assert bus1 is bus2

    MarketDataBus.reset()
    bus3 = MarketDataBus.get_instance()
    assert bus3 is not None


def test_market_data_bus_seeding_and_retrieval() -> None:
    MarketDataBus.reset()
    bus = MarketDataBus.get_instance()

    now = int(datetime.now(timezone.utc).timestamp())
    records = [
        {"timestamp": now - 300, "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 10.0},
        {"timestamp": now - 240, "open": 102.0, "high": 106.0, "low": 101.0, "close": 104.0, "volume": 12.0},
        {"timestamp": now - 180, "open": 104.0, "high": 108.0, "low": 103.0, "close": 107.0, "volume": 15.0},
    ]

    count = bus.seed_from_records("EURUSD", "M1", records)
    assert count == 3

    candles = bus.get_latest_candles("EURUSD", "M1", count=2)
    assert len(candles) == 2
    assert candles[-1]["close"] == 107.0

    df = bus.get_candles_df("EURUSD", "M1")
    assert df is not None
    assert len(df) == 3
    assert list(df["close"].values) == [102.0, 104.0, 107.0]


def test_market_data_bus_on_tick() -> None:
    MarketDataBus.reset()
    bus = MarketDataBus.get_instance()

    # Pre-seed buffer so on_tick knows the buffer exists
    now_dt = datetime.now(timezone.utc)
    now_ts = int(now_dt.timestamp())
    bus.seed_from_records(
        "XAUUSD",
        "M1",
        [{"timestamp": now_ts - 60, "open": 2000.0, "high": 2005.0, "low": 1995.0, "close": 2002.0, "volume": 1.0}],
    )

    # Stream tick
    bus.on_tick("XAUUSD", bid=2003.0, ask=2003.5, last=2003.25, timestamp=now_dt)

    df = bus.get_candles_df("XAUUSD", "M1")
    assert df is not None
    assert len(df) >= 1
    assert df["close"].iloc[-1] == 2003.25
