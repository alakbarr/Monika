# ==============================================================================
# File: domain/ports/market_data.py
# ==============================================================================

"""
Domain Market Data Port.

Defines pure abstract interfaces for live quotes, historical price bars,
and order book / liquidity depth (Dependency Inversion Principle).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class MarketDataPort(Protocol):
    """Standardized pure domain protocol for market data feeds."""

    async def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current quote for a symbol."""
        ...

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = "H1",
        count: int = 100,
    ) -> Any:
        """Retrieve historical OHLCV price bars."""
        ...

    async def get_order_book(self, symbol: str) -> Dict[str, Any]:
        """Retrieve current order book depth / market liquidity."""
        ...
