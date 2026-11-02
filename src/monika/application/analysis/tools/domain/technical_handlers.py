"""Technical domain tool handlers (OHLCV, Indicators, SMC, Fibonacci, ATR)."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.TechnicalHandlers")


class TechnicalToolHandlers:
    """Handlers for technical price action, indicators, and market structure."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def get_market_quote(self, symbol: str, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_market_quote

        return await handle_get_market_quote({"symbol": symbol, **kwargs}, session=session, settings=self.settings)

    async def get_price_history(
        self, symbol: str, timeframe: str = "H4", count: int = 100, session: Optional[AsyncSession] = None, **kwargs
    ) -> Any:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

        effective_count = kwargs.get("limit") or count
        client = kwargs.get("mt5_client") or get_mt5_client(self.settings)
        if client and hasattr(client, "get_rates"):
            import inspect

            res = client.get_rates(symbol=symbol, timeframe=timeframe, count=effective_count)
            if inspect.iscoroutine(res):
                return await res
            return res

        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_price_history

        return await handle_get_price_history(
            {"symbol": symbol, "timeframe": timeframe, "count": effective_count, **kwargs},
            session=session,
            settings=self.settings,
        )

    async def get_technical_indicators(
        self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_technical_indicators

        return await handle_get_technical_indicators(
            {"symbol": symbol, "timeframe": timeframe, **kwargs}, session=session, settings=self.settings
        )

    async def get_atr(
        self, symbol: str, timeframe: str = "H4", period: int = 14, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        if session:
            from monika.domain.indicators.technical import TechnicalIndicatorCalculator

            calc = TechnicalIndicatorCalculator(session, self.settings)
            snapshot = await calc.get_snapshot(symbol, timeframe)
            atr_val = None
            if snapshot:
                target_key = f"ATR_{period}"
                atr_dict = snapshot.get(target_key) or snapshot.get("ATR") or {}
                atr_val = atr_dict.get("value") if isinstance(atr_dict, dict) else None
                if atr_val is None and isinstance(atr_dict, dict):
                    atr_val = atr_dict.get("atr")
            return {"symbol": symbol, "timeframe": timeframe, "period": period, "atr": atr_val}
        return {"symbol": symbol, "timeframe": timeframe, "period": period, "status": "no_session"}

    async def get_smc_zones(
        self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        if session:
            from sqlalchemy import or_, select

            from monika.core.primitives import clock
            from monika.infrastructure.database.models import FVGZone, OrderBlock, SRZone

            now_dt = clock.now()
            include_mitigated = kwargs.get("include_mitigated", False)

            sr_stmt = select(SRZone).where(SRZone.symbol == symbol, SRZone.timeframe == timeframe)
            sr_stmt = sr_stmt.where(or_(SRZone.last_touched.is_(None), SRZone.last_touched <= now_dt)).limit(10)
            sr_rows = (await session.execute(sr_stmt)).scalars().all()

            ob_stmt = select(OrderBlock).where(
                OrderBlock.symbol == symbol,
                OrderBlock.timeframe == timeframe,
                OrderBlock.formed_at <= now_dt,
            )
            if not include_mitigated:
                ob_stmt = ob_stmt.where(or_(OrderBlock.mitigated_at.is_(None), OrderBlock.mitigated_at > now_dt))
            ob_stmt = ob_stmt.order_by(OrderBlock.formed_at.desc()).limit(10)
            ob_rows = (await session.execute(ob_stmt)).scalars().all()

            fvg_stmt = select(FVGZone).where(
                FVGZone.symbol == symbol,
                FVGZone.timeframe == timeframe,
                FVGZone.formed_at <= now_dt,
            )
            if not include_mitigated:
                fvg_stmt = fvg_stmt.where(or_(FVGZone.filled_at.is_(None), FVGZone.filled_at > now_dt))
            fvg_stmt = fvg_stmt.order_by(FVGZone.formed_at.desc()).limit(10)
            fvg_rows = (await session.execute(fvg_stmt)).scalars().all()

            formatted_fvg = [
                {
                    "gap_high": r.gap_high,
                    "gap_low": r.gap_low,
                    "direction": r.direction,
                    "filled": bool(r.filled_at and r.filled_at <= now_dt),
                }
                for r in fvg_rows
            ]
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
                        "mitigated": bool(r.mitigated_at and r.mitigated_at <= now_dt),
                    }
                    for r in ob_rows
                ],
                "fvg_zones": formatted_fvg,
                "fair_value_gaps": formatted_fvg,
                "total_order_blocks": len(ob_rows),
                "total_fvg_zones": len(fvg_rows),
            }
        return {"symbol": symbol, "timeframe": timeframe, "status": "no_session"}

    async def get_structure_breaks(
        self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        if session:
            from sqlalchemy import select

            from monika.infrastructure.database.models import StructureBreak

            breaks = (
                (
                    await session.execute(
                        select(StructureBreak)
                        .where(StructureBreak.symbol == symbol, StructureBreak.timeframe == timeframe)
                        .order_by(StructureBreak.formed_at.desc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "breaks": [
                    {
                        "type": b.type,
                        "direction": getattr(b, "direction", None),
                        "price": getattr(b, "price", getattr(b, "broken_price", None)),
                        "broken_price": getattr(b, "price", getattr(b, "broken_price", None)),
                        "formed_at": b.formed_at.isoformat() if hasattr(b.formed_at, "isoformat") else str(b.formed_at),
                    }
                    for b in breaks
                ],
            }
        return {"symbol": symbol, "timeframe": timeframe, "status": "no_session"}

    async def get_fibonacci_levels(
        self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_fibonacci_levels

        return await handle_get_fibonacci_levels(
            {"symbol": symbol, "timeframe": timeframe, **kwargs}, session=session, settings=self.settings
        )

    async def get_daily_range_context(
        self, symbol: str, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_daily_range_context

        return await handle_get_daily_range_context(
            {"symbol": symbol, **kwargs}, session=session, settings=self.settings
        )

    async def get_optimal_intraday_levels(
        self, symbol: str, direction: str, entry_price: float, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_optimal_intraday_levels

        return await handle_get_optimal_intraday_levels(
            {"symbol": symbol, "direction": direction, "entry_price": entry_price, **kwargs},
            session=session,
            settings=self.settings,
        )

    async def get_pivot_points(
        self,
        symbol: str,
        method: str = "classic",
        timeframe: str = "D1",
        session: Optional[AsyncSession] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_pivot_points

        return await handle_get_pivot_points(
            {"symbol": symbol, "method": method, "timeframe": timeframe, **kwargs},
            session=session,
            settings=self.settings,
        )

    async def get_ichimoku(
        self, symbol: str, timeframe: str = "H4", session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_ichimoku

        return await handle_get_ichimoku(
            {"symbol": symbol, "timeframe": timeframe, **kwargs}, session=session, settings=self.settings
        )

    async def scan_chart_patterns(
        self, symbol: str, timeframe: str = "H4", order: int = 5, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_scan_chart_patterns

        return await handle_scan_chart_patterns(
            {"symbol": symbol, "timeframe": timeframe, "order": order, **kwargs},
            session=session,
            settings=self.settings,
        )

    async def get_seasonality(
        self, symbol: str, type: str = "all", session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_seasonality

        return await handle_get_seasonality(
            {"symbol": symbol, "type": type, **kwargs}, session=session, settings=self.settings
        )

    async def get_divergences(
        self, symbol: str, timeframes: Optional[list] = None, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_divergences

        return await handle_get_divergences(
            {"symbol": symbol, "timeframes": timeframes or ["H1", "H4"], **kwargs},
            session=session,
            settings=self.settings,
        )
