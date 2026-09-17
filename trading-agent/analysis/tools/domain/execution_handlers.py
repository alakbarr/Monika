"""Execution and sizing domain tool handlers."""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.ExecutionHandlers")


class ExecutionToolHandlers:
    """Handlers for execution proposals, spread inspection, and deterministic position sizing."""

    def __init__(self, settings: Optional[dict] = None, mt5_client: Optional[Any] = None):
        self.settings = settings or {}
        self.mt5_client = mt5_client

    async def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        risk_pct: float = 1.0,
        session: Optional[AsyncSession] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Deterministic position sizing implementation.
        Computes exact lot size based on account balance and risk formula.
        """
        from risk.position_sizing import calculate_lot_size
        mt5 = kwargs.pop("mt5_client", None) or self.mt5_client
        if mt5 is None and self.settings:
            try:
                from execution.mt5_client import get_mt5_client
                mt5 = get_mt5_client(self.settings)
            except Exception:
                mt5 = None

        return await calculate_lot_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_pct=risk_pct,
            session=session,
            settings=self.settings,
            mt5_client=mt5,
            **kwargs
        )

    async def get_spread_snapshot(self, symbol: Optional[str] = None, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if kwargs.get("symbols") or (session and not kwargs.get("mock_only")):
            from analysis.tools.handlers.market_data_tools import handle_get_spread_snapshot
            return await handle_get_spread_snapshot({"symbol": symbol, **kwargs}, session=session, settings=self.settings)
        if self.mt5_client is not None:
            client = self.mt5_client
        else:
            from execution.mt5_client import get_mt5_client
            client = get_mt5_client(self.settings)
        return await client.get_spread(symbol=symbol or "EURUSD")

