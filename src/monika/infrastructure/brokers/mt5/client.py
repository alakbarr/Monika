"""
Composite MT5Client coordinating connection, market data, and execution mixins.
"""

from typing import Any, Optional

from .connection import MT5ConnectionMixin
from .execution import MT5ExecutionMixin
from .market_data import MT5MarketDataMixin


class MT5Client(MT5ConnectionMixin, MT5MarketDataMixin, MT5ExecutionMixin):
    """Pembungkus async untuk library MetaTrader5 Python dengan dukungan Redundant Secondary Failover Gateway."""

    pass


_default_mt5_client: Optional[MT5Client] = None


def get_mt5_client(settings: Optional[dict[str, Any]] = None) -> MT5Client:
    """Singleton getter untuk instance MT5Client."""
    global _default_mt5_client
    if _default_mt5_client is None:
        _default_mt5_client = MT5Client(settings=settings or {})
    return _default_mt5_client
