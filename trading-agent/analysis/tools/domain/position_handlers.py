"""Position, portfolio, and risk inspection tool handlers."""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

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

        # Enrich positions with live price, pips to SL, and pips to TP
        if positions:
            for p in positions:
                sym = p.get("symbol")
                if not sym:
                    continue
                cur_p = p.get("price_current")
                if not cur_p:
                    try:
                        client = get_mt5_client(self.settings)
                        if client:
                            tick = await client.get_symbol_ticker(sym)
                            if tick:
                                cur_p = tick.get("bid") if p.get("direction", "").lower() == "buy" else tick.get("ask")
                    except Exception:
                        pass
                if not cur_p and session:
                    try:
                        from database.models import PriceOHLCV
                        last_bar = (await session.execute(
                            select(PriceOHLCV).where(PriceOHLCV.symbol == sym).order_by(PriceOHLCV.timestamp.desc()).limit(1)
                        )).scalar_one_or_none()
                        if last_bar:
                            cur_p = float(last_bar.close)
                    except Exception:
                        pass

                if cur_p:
                    cur_p = float(cur_p)
                    p["price_current"] = round(cur_p, 5)
                    pip_size = 0.01 if ("JPY" in sym or "XAU" in sym or "BTC" in sym) else 0.0001
                    sl = p.get("stop_loss")
                    tp = p.get("take_profit")
                    entry = p.get("entry_price")
                    if sl is not None:
                        p["pips_to_sl"] = round(abs(cur_p - float(sl)) / pip_size, 1)
                    if tp is not None:
                        p["pips_to_tp"] = round(abs(float(tp) - cur_p) / pip_size, 1)
                    if entry is not None and (p.get("pnl") is None or p.get("pnl_usd") is None):
                        direction = (p.get("direction") or "buy").lower()
                        price_diff = (cur_p - float(entry)) if direction == "buy" else (float(entry) - cur_p)
                        lots = float(p.get("lots") or 0.01)
                        contract_size = 100 if "XAU" in sym else 100000
                        floating_usd = round(price_diff * lots * contract_size, 2)
                        p["unrealized_pnl_usd"] = floating_usd
                        if p.get("pnl") is None:
                            p["pnl"] = floating_usd

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
        cur_balance = init_balance
        cur_equity = init_balance

        if session:
            try:
                from database.models import PaperTradeRecord
                closed_pnl = (await session.execute(
                    select(func.sum(PaperTradeRecord.pnl_usd))
                    .where(PaperTradeRecord.status == "closed")
                )).scalar_one_or_none()
                if closed_pnl is not None:
                    cur_balance = round(init_balance + float(closed_pnl), 2)
                else:
                    closed_pct = (await session.execute(
                        select(func.sum(PaperTradeRecord.pnl_pct))
                        .where(PaperTradeRecord.status == "closed")
                    )).scalar_one_or_none()
                    if closed_pct is not None:
                        cur_balance = round(init_balance * (1.0 + float(closed_pct) / 100.0), 2)

                open_trades = (await session.execute(
                    select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
                )).scalars().all()
                floating_pnl = 0.0
                for ot in open_trades:
                    if getattr(ot, "pnl_usd", None) is not None:
                        floating_pnl += float(ot.pnl_usd)
                    elif getattr(ot, "pnl_pct", None) is not None:
                        floating_pnl += (float(ot.pnl_pct) / 100.0) * init_balance
                cur_equity = round(cur_balance + floating_pnl, 2)
            except Exception as pe:
                logger.debug(f"[PositionToolHandlers] Paper balance calculation: {pe}")

        return {
            "mode": "paper_trading",
            "balance": cur_balance,
            "equity": cur_equity,
            "margin": 0.0,
            "free_margin": cur_equity,
            "margin_level": 100.0,
            "margin_mode": "hedging",
            "allow_hedging": True,
            "currency": paper_cfg.get("currency", "USD"),
            "status": "active_simulation",
        }

    async def get_risk_state(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from risk.risk_gate import get_current_risk_state
        return await get_current_risk_state(session=session)
