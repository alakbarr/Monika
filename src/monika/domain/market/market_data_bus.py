"""
Monika In-Memory Real-Time Market Data Bus.

Provides a unified high-performance facade over CandleRingBuffer and RingBufferHub.
Offers read-through caching, sub-millisecond candle retrieval, and thread-safe streaming updates.
"""

from __future__ import annotations

from datetime import datetime
import threading
from typing import Any, Optional, Sequence

import pandas as pd
import polars as pl

from monika.domain.market.candle_ring_buffer import RingBufferHub


class MarketDataBus:
    """
    Unified In-Memory Market Data Bus.
    Acts as the single source of truth for ultra-low latency OHLCV bar access in Monika.
    """

    _instance: Optional[MarketDataBus] = None
    _lock = threading.RLock()

    def __init__(self, hub: Optional[RingBufferHub] = None):
        self._hub = hub or RingBufferHub.get_instance()

    @classmethod
    def get_instance(cls) -> MarketDataBus:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance._hub.clear_all()
            cls._instance = None

    def get_candles_df(
        self,
        symbol: str,
        timeframe: str,
        count: Optional[int] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Retrieve recent candles as a pandas DataFrame directly from in-memory ring buffers.
        Zero DB roundtrips, sub-millisecond retrieval.
        """
        return self._hub.get_latest_dataframe(symbol, timeframe, count=count)

    def get_candles_polars(
        self,
        symbol: str,
        timeframe: str,
        count: Optional[int] = None,
    ) -> Optional[pl.DataFrame]:
        """
        Retrieve recent candles as a high-throughput Polars DataFrame directly from in-memory ring buffers.
        Zero intermediate Python object allocations.
        """
        return self._hub.get_latest_polars(symbol, timeframe, count=count)

    def get_latest_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """Returns the UTC epoch timestamp of the latest candle in memory, or None."""
        return self._hub.get_latest_timestamp(symbol, timeframe)

    def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve recent candles as a list of dicts directly from memory."""
        return self._hub.get_latest_candles(symbol, timeframe, count=count)

    def seed_from_records(
        self,
        symbol: str,
        timeframe: str,
        rows: Sequence[Any],
    ) -> int:
        """Seed or append OHLCV records to the in-memory buffer."""
        return self._hub.update_from_ohlcv_rows(symbol, timeframe, rows)

    def on_tick(
        self,
        symbol: str,
        bid: float,
        ask: float,
        last: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Stream tick arrival into forming bars in memory."""
        self._hub.on_tick(symbol=symbol, bid=bid, ask=ask, last=last, timestamp=timestamp)

    def has_sufficient_bars(self, symbol: str, timeframe: str, min_bars: int = 50) -> bool:
        """Check if buffer has at least min_bars available."""
        buf = self._hub.get_buffer(symbol, timeframe)
        return buf.size >= min_bars


__all__ = [
    "MarketDataBus",
]
