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
        positions = []
        try:
            client = get_mt5_client(self.settings)
            if client:
                positions = await client.get_open_positions()
        except Exception as e:
            logger.debug(f"[PositionToolHandlers] MT5 get_open_positions error: {e}")
            positions = []

        if not positions and session:
            try:
                from database.models import Position, PaperTradeRecord
                from sqlalchemy import select
                db_pos = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                if db_pos:
                    positions = [p.to_dict() if hasattr(p, "to_dict") else {
                        "ticket": getattr(p, "mt5_ticket", getattr(p, "id", None)),
                        "symbol": p.symbol,
                        "direction": p.direction,
                        "lots": getattr(p, "volume", getattr(p, "lots", 0.01)),
                        "entry_price": p.entry_price,
                        "stop_loss": getattr(p, "sl", getattr(p, "stop_loss", None)),
                        "take_profit": getattr(p, "tp", getattr(p, "take_profit", None)),
                        "status": p.status,
                        "pnl": getattr(p, "pnl", getattr(p, "unrealized_pnl", None)),
                    } for p in db_pos]
                else:
                    paper_pos = (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open"))).scalars().all()
                    if paper_pos:
                        positions = [{
                            "ticket": f"PAPER-{p.id}",
                            "symbol": p.symbol,
                            "direction": p.direction,
                            "lots": getattr(p, "requested_lot", getattr(p, "volume", getattr(p, "lots", 0.01))),
                            "entry_price": p.entry_price,
                            "stop_loss": getattr(p, "stop_loss", getattr(p, "sl", None)),
                            "take_profit": getattr(p, "take_profit", getattr(p, "tp", None)),
                            "status": "paper_open",
                            "pnl": getattr(p, "pnl_pct", None),
                        } for p in paper_pos]
            except Exception as dbe:
                logger.debug(f"[PositionToolHandlers] DB fallback error: {dbe}")

        return positions

    async def get_pending_orders(self, symbol: Optional[str] = None, session: Optional[AsyncSession] = None, **kwargs) -> Any:
        from execution.mt5_client import get_mt5_client
        orders = []
        try:
            client = get_mt5_client(self.settings)
            if client:
                orders = await client.get_orders(symbol=symbol)
        except Exception as e:
            logger.debug(f"[PositionToolHandlers] MT5 get_pending_orders error: {e}")
            orders = []
        return orders

    async def get_account_info(self, session: Optional[AsyncSession] = None, **kwargs) -> Optional[Dict[str, Any]]:
        from execution.mt5_client import get_mt5_client
        info = None
        try:
            client = get_mt5_client()
            if client:
                info = await client.get_account_info()
        except Exception as e:
            logger.debug(f"[PositionToolHandlers] MT5 get_account_info notice: {e}")

        if info and isinstance(info, dict) and (info.get("balance", 0) > 0 or info.get("equity", 0) > 0):
            return info

        # Fallback to paper trading account simulation if MT5 is offline/paper mode
        paper_cfg = self.settings.get("paper_trading", {})
        init_balance = float(paper_cfg.get("initial_balance", 10000.0))
        return {
            "mode": "paper_trading",
            "balance": init_balance,
            "equity": init_balance,
            "margin": 0.0,
            "free_margin": init_balance,
            "margin_level": 100.0,
            "currency": paper_cfg.get("currency", "USD"),
            "status": "active_simulation",
        }

    async def get_risk_state(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from risk.risk_gate import get_current_risk_state
        return await get_current_risk_state(session=session)
