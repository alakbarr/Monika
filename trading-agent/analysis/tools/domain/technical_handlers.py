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
        from analysis.tools.handlers.market_data_tools import handle_get_technical_indicators
        return await handle_get_technical_indicators({"symbol": symbol, "timeframe": timeframe, **kwargs}, session=session, settings=self.settings)

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
            ob_rows = (await session.execute(select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe).order_by(OrderBlock.formed_at.desc()).limit(10))).scalars().all()
            fvg_rows = (await session.execute(select(FVGZone).where(FVGZone.symbol == symbol, FVGZone.timeframe == timeframe).order_by(FVGZone.formed_at.desc()).limit(10))).scalars().all()
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "sr_zones": [
                    {"price_high": r.price_high, "price_low": r.price_low, "strength": getattr(r, "strength", 1.0)}
                    for r in sr_rows
                ],
                "order_blocks": [
                    {
                        "price_high": r.price_high,
                        "price_low": r.price_low,
                        "direction": r.direction,
                        "mitigated": r.mitigated_at is not None,
                    }
                    for r in ob_rows
                ],
                "fvg_zones": [
                    {
                        "gap_high": r.gap_high,
                        "gap_low": r.gap_low,
                        "direction": r.direction,
                        "filled": r.filled_at is not None,
                    }
                    for r in fvg_rows
                ],
                "total_order_blocks": len(ob_rows),
                "total_fvg_zones": len(fvg_rows)
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

    async def get_pivot_points(self, symbol: str, method: str = "classic", timeframe: str = "D1", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_pivot_points
        return await handle_get_pivot_points({"symbol": symbol, "method": method, "timeframe": timeframe, **kwargs}, session=session, settings=self.settings)

    async def get_ichimoku(self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_ichimoku
        return await handle_get_ichimoku({"symbol": symbol, "timeframe": timeframe, **kwargs}, session=session, settings=self.settings)

    async def scan_chart_patterns(self, symbol: str, timeframe: str = "H4", order: int = 5, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_scan_chart_patterns
        return await handle_scan_chart_patterns({"symbol": symbol, "timeframe": timeframe, "order": order, **kwargs}, session=session, settings=self.settings)

    async def get_seasonality(self, symbol: str, type: str = "all", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_seasonality
        return await handle_get_seasonality({"symbol": symbol, "type": type, **kwargs}, session=session, settings=self.settings)

    async def get_divergences(self, symbol: str, timeframes: Optional[list] = None, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.market_data_tools import handle_get_divergences
        return await handle_get_divergences({"symbol": symbol, "timeframes": timeframes or ["H1", "H4"], **kwargs}, session=session, settings=self.settings)

