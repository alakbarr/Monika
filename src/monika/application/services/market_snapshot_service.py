# ==============================================================================
# File: application/services/market_snapshot_service.py
# Description: In-memory high-throughput market ground-truth snapshot service.
# ==============================================================================

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.MarketSnapshotService")


@dataclass
class AssetMarketSnapshot:
    """Ground truth market bar & indicator snapshot for a symbol and timeframe."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    indicators: Dict[str, float] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.monotonic)

    def is_fresh(self, max_age_seconds: float = 300.0) -> bool:
        """Check if snapshot was refreshed within max_age_seconds."""
        return (time.monotonic() - self.updated_at) <= max_age_seconds

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary matching VerifiedMarketSnapshot format."""
        d = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "verified_at": self.timestamp.isoformat(),
            "_ground_truth": True,
            "latest_open": self.open,
            "latest_high": self.high,
            "latest_low": self.low,
            "latest_close": self.close,
            "volume": self.volume,
            "bar_timestamp": self.timestamp.isoformat(),
        }
        d.update(self.indicators)
        return d


class MarketSnapshotService:
    """Thread-safe in-memory cache for asset ground-truth snapshots."""

    _instance: Optional[MarketSnapshotService] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._snapshots: Dict[Tuple[str, str], AssetMarketSnapshot] = {}
        self._access_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> MarketSnapshotService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for test hermeticity)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.clear()
            cls._instance = None

    def set_snapshot(
        self,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        indicators: Optional[Dict[str, float]] = None,
    ) -> AssetMarketSnapshot:
        """Store or update in-memory snapshot for a symbol/timeframe."""
        sym = symbol.strip().upper().replace("/", "")
        tf = timeframe.strip().upper()
        snap = AssetMarketSnapshot(
            symbol=sym,
            timeframe=tf,
            timestamp=timestamp,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            indicators=indicators or {},
            updated_at=time.monotonic(),
        )
        with self._access_lock:
            self._snapshots[(sym, tf)] = snap
        return snap

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str = "H1",
        max_age_seconds: float = 300.0,
    ) -> Optional[AssetMarketSnapshot]:
        """Retrieve cached snapshot if present and unexpired."""
        sym = symbol.strip().upper().replace("/", "")
        tf = timeframe.strip().upper()
        with self._access_lock:
            snap = self._snapshots.get((sym, tf))
            if snap is not None and snap.is_fresh(max_age_seconds):
                return snap
            return None

    def clear(self) -> int:
        """Clear all snapshots."""
        with self._access_lock:
            c = len(self._snapshots)
            self._snapshots.clear()
            return c
