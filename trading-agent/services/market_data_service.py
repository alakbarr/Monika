# ==============================================================================
# File: services/market_data_service.py
# ==============================================================================

"""
Market Data Application Service.
Provides uniform access to symbol quotes, ticks, and liquidity status
abstracted from MT5 client or historical data providers.
"""

from typing import Dict, Any, Optional
import logging

from utils.infra.container import ServiceContainer, get_container

logger = logging.getLogger("TradingAgent.Services.MarketData")


class MarketDataService:
    """Service providing unified quote and market data access."""

    @staticmethod
    def get_latest_quote(
        symbol: str,
        container: Optional[ServiceContainer] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch current bid/ask quote for a symbol."""
        c = container or get_container()
        mt5_client = c.get("mt5_client")
        if not mt5_client:
            return None

        sym = symbol.upper()
        try:
            if hasattr(mt5_client, "get_quote"):
                return mt5_client.get_quote(sym)
            elif hasattr(mt5_client, "get_symbol_info_tick"):
                tick = mt5_client.get_symbol_info_tick(sym)
                if tick:
                    return {
                        "symbol": sym,
                        "bid": getattr(tick, "bid", 0.0),
                        "ask": getattr(tick, "ask", 0.0),
                        "spread": round((getattr(tick, "ask", 0.0) - getattr(tick, "bid", 0.0)), 5),
                    }
        except Exception as e:
            logger.debug(f"[MarketDataService] Quote fetch note for {sym}: {e}")
        return None
