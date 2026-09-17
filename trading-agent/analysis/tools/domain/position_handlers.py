"""Position, portfolio, and risk inspection tool handlers."""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.PositionHandlers")


class PositionToolHandlers:
    """Handlers for account, position, and risk state inspection."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def get_open_positions(self, session: Optional[AsyncSession] = None, **kwargs) -> Any:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        return await client.get_open_positions()

    async def get_account_info(self, session: Optional[AsyncSession] = None, **kwargs) -> Optional[Dict[str, Any]]:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        return await client.get_account_info()

    async def get_risk_state(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from risk.risk_gate import get_current_risk_state
        return await get_current_risk_state(session=session)
