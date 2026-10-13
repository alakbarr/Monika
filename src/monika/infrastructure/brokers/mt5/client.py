"""
Composite MT5Client coordinating connection, market data, and execution mixins.
"""

from typing import Any, Optional

from .connection import MT5ConnectionMixin
from .execution import MT5ExecutionMixin
from .market_data import MT5MarketDataMixin


class MT5Client(MT5ConnectionMixin, MT5MarketDataMixin, MT5ExecutionMixin):
    """Pembungkus async untuk library MetaTrader5 Python dengan dukungan Redundant Secondary Failover Gateway."""

    _instance: Optional["MT5Client"] = None

    @classmethod
    def get_instance(cls, settings: Optional[dict[str, Any]] = None) -> "MT5Client":
        if cls._instance is None:
            cls._instance = cls(settings=settings or {})
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None


def get_mt5_client(settings: Optional[dict[str, Any]] = None) -> MT5Client:
    """Singleton getter untuk instance MT5Client."""
    return MT5Client.get_instance(settings=settings)
