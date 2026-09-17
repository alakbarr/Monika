# ==============================================================================
# File: analysis/tools/handlers/timesfm.py
# ==============================================================================

"""
TimesFM tool handler: quantiles, trend, and confidence via Google TimesFM 3.0.
Self-registering modular handler with direct execution (no circular trampoline).
"""

import logging
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool

logger = logging.getLogger("TradingAgent.Tools.TimesFM")


async def handle_get_timesfm_forecast(
    symbol: Optional[Any] = None,
    timeframe: str = "H1",
    horizon_steps: int = 24,
    session: Optional[AsyncSession] = None,
    settings: Optional[dict] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> dict:
    """Ambil proyeksi kuantil harga (Q10, Q50, Q90), trend, dan confidence via Google TimesFM 3.0."""
    effective_session = session or getattr(executor, "session", None)
    effective_settings = settings or getattr(executor, "settings", {}) or {}

    if isinstance(symbol, dict):
        inp = symbol
        resolved = None
        if executor and hasattr(executor, "_resolve_symbol"):
            resolved = executor._resolve_symbol(inp)
        sym = resolved or inp.get("symbol") or getattr(executor, "symbol", None)
        tf = inp.get("timeframe") or timeframe
        hs = int(inp.get("horizon_steps") or horizon_steps)
    else:
        sym = symbol or kwargs.get("symbol") or getattr(executor, "symbol", None)
        tf = kwargs.get("timeframe", timeframe)
        hs = int(kwargs.get("horizon_steps", horizon_steps))

    if not sym:
        return {
            "status": "error",
            "error": "Symbol is required for TimesFM forecast.",
            "trend": "NEUTRAL",
            "confidence": 0.0,
        }

    sym = str(sym).strip().upper().replace("/", "")

    if not effective_session:
        return {
            "symbol": sym,
            "timeframe": tf,
            "status": "no_session",
            "message": f"Database session required for TimesFM forecast on {sym}.",
            "trend": "NEUTRAL",
            "confidence": 0.0,
        }

    try:
        from indicators.timesfm_engine import TimesFMEngine
        engine = TimesFMEngine(effective_settings)
        forecast = await engine.get_or_generate_forecast(effective_session, symbol=sym, timeframe=tf, horizon=hs)

        if not forecast:
            return {
                "symbol": sym,
                "timeframe": tf,
                "status": "unavailable",
                "message": f"TimesFM forecast unavailable for {sym} ({tf}). Insufficient historical data or engine disabled.",
                "trend": "NEUTRAL",
                "confidence": 0.0,
            }

        quantiles = forecast.get("quantiles", {})
        q10_list = quantiles.get("q10", [])
        q50_list = quantiles.get("q50", [])
        q90_list = quantiles.get("q90", [])
        current_price = float(forecast.get("current_price") or (q50_list[0] if q50_list else 0.0))
        q10 = float(q10_list[-1]) if q10_list else None
        q50 = float(q50_list[-1]) if q50_list else None
        q90 = float(q90_list[-1]) if q90_list else None

        trend = "NEUTRAL"
        if q50 is not None and current_price > 0:
            price_change = (q50 - current_price) / current_price
            if price_change > 0.0015:
                trend = "BULLISH"
            elif price_change < -0.0015:
                trend = "BEARISH"

        skew = float(forecast.get("quantile_skew", 0.0))
        confidence = round(min(0.95, max(0.50, 0.75 - abs(skew) * 0.25)), 2)

        alpha_skew = None
        try:
            from analysis.calculators.timesfm_alpha import TimesFMAlphaCalculator
            if quantiles:
                alpha_skew = TimesFMAlphaCalculator.calculate_skew_from_quantiles(quantiles, current_price=current_price)
        except Exception as alpha_err:
            logger.debug(f"[{sym}] TimesFM tool alpha calculation note: {alpha_err}")

        return {
            "status": "success",
            "symbol": sym,
            "timeframe": tf,
            "horizon_steps": hs,
            "current_price": current_price,
            "q10_lower_bound": q10,
            "q50_median": q50,
            "q90_upper_bound": q90,
            "expected_range": forecast.get("expected_range"),
            "quantile_skew": skew,
            "volatility_expansion_ratio": forecast.get("volatility_expansion_ratio"),
            "alpha_analysis": alpha_skew,
            "trend": trend,
            "trend_direction": trend,
            "confidence": confidence,
        }
    except Exception as e:
        logger.error(f"[{sym}] TimesFM tool error: {e}", exc_info=True)
        return {
            "status": "error",
            "symbol": sym,
            "error": str(e),
            "trend": "NEUTRAL",
            "confidence": 0.0,
        }


@register_tool("get_timesfm_forecast", aliases=["timesfm_forecast", "timesfm"], category="TECHNICAL", parallel_safe=True)
class GetTimesFMForecastHandler(ToolHandler):
    name = "get_timesfm_forecast"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_timesfm_forecast(symbol=args, session=session, executor=executor, **kwargs)
