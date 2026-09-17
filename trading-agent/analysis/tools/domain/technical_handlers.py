"""Technical domain tool handlers (OHLCV, Indicators, SMC, Fibonacci, ATR)."""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.TechnicalHandlers")


class TechnicalToolHandlers:
    """Handlers for technical price action, indicators, and market structure."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def get_market_quote(self, symbol: str, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_market_quote
        return await handle_get_market_quote({"symbol": symbol, **kwargs}, session=session, settings=self.settings)

    async def get_price_history(self, symbol: str, timeframe: str = "H4", count: int = 100, session: Optional[AsyncSession] = None, **kwargs) -> Any:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        return await client.get_rates(symbol=symbol, timeframe=timeframe, count=count)

    async def get_technical_indicators(self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if session:
            from indicators.technical import TechnicalIndicatorCalculator
            calc = TechnicalIndicatorCalculator(session, self.settings)
            snapshot = await calc.get_snapshot(symbol, timeframe)
            return {"symbol": symbol, "timeframe": timeframe, "indicators": snapshot or {}}
        return {"symbol": symbol, "timeframe": timeframe, "indicators": {}, "status": "no_session"}

    async def get_atr(self, symbol: str, timeframe: str = "H4", period: int = 14, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if session:
            from indicators.technical import TechnicalIndicatorCalculator
            calc = TechnicalIndicatorCalculator(session, self.settings)
            snapshot = await calc.get_snapshot(symbol, timeframe)
            atr_val = (snapshot.get("ATR", {}) or {}).get("value") if snapshot else None
            return {"symbol": symbol, "timeframe": timeframe, "period": period, "atr": atr_val}
        return {"symbol": symbol, "timeframe": timeframe, "period": period, "status": "no_session"}

    async def get_smc_zones(self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if session:
            from database.models import SRZone, OrderBlock, FVGZone
            from sqlalchemy import select
            sr_rows = (await session.execute(select(SRZone).where(SRZone.symbol == symbol, SRZone.timeframe == timeframe).limit(10))).scalars().all()
            ob_rows = (await session.execute(select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe).limit(10))).scalars().all()
            fvg_rows = (await session.execute(select(FVGZone).where(FVGZone.symbol == symbol, FVGZone.timeframe == timeframe).limit(10))).scalars().all()
            return {
                "symbol": symbol, "timeframe": timeframe,
                "sr_zones": [
                    {"price_high": r.price_high, "price_low": r.price_low, "strength": r.strength}
                    for r in sr_rows
                ],
                "order_blocks": len(ob_rows),
                "fvg_zones": len(fvg_rows)
            }
        return {"symbol": symbol, "timeframe": timeframe, "status": "no_session"}

    async def get_structure_breaks(self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if session:
            from database.models import StructureBreak
            from sqlalchemy import select
            breaks = (await session.execute(select(StructureBreak).where(StructureBreak.symbol == symbol, StructureBreak.timeframe == timeframe).order_by(StructureBreak.formed_at.desc()).limit(5))).scalars().all()
            return {"symbol": symbol, "timeframe": timeframe, "breaks": [b.type for b in breaks]}
        return {"symbol": symbol, "timeframe": timeframe, "status": "no_session"}

    async def get_fibonacci_levels(self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_fibonacci_levels
        return await handle_get_fibonacci_levels({"symbol": symbol, "timeframe": timeframe, **kwargs}, session=session, settings=self.settings)


    async def get_daily_range_context(self, symbol: str, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_daily_range_context
        return await handle_get_daily_range_context({"symbol": symbol, **kwargs}, session=session, settings=self.settings)

    async def get_optimal_intraday_levels(self, symbol: str, direction: str, entry_price: float, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_optimal_intraday_levels
        return await handle_get_optimal_intraday_levels({"symbol": symbol, "direction": direction, "entry_price": entry_price, **kwargs}, session=session, settings=self.settings)
