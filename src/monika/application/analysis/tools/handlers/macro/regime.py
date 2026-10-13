# ==============================================================================
# File: analysis/tools/handlers/macro/regime.py
# ==============================================================================

"""
Market sessions, volatility regime, macro bias score, and ADX market regime handlers.
"""

import json
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.macro.base import _get_macro_context, logger
from monika.infrastructure.database.models import TechnicalIndicator


async def handle_get_market_session(args: dict, **ctx) -> dict:
    now = clock.now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # DST-aware time zones
    tokyo_tz = ZoneInfo("Asia/Tokyo")
    london_tz = ZoneInfo("Europe/London")
    ny_tz = ZoneInfo("America/New_York")

    tokyo_now = now.astimezone(tokyo_tz)
    london_now = now.astimezone(london_tz)
    ny_now = now.astimezone(ny_tz)

    sessions = []
    if 9 <= tokyo_now.hour < 18:
        sessions.append("Tokyo")
    if 8 <= london_now.hour < 16 or (london_now.hour == 16 and london_now.minute <= 30):
        sessions.append("London")
    if 8 <= ny_now.hour < 17:
        sessions.append("New York")

    overlap = "London-NY" if ("London" in sessions and "New York" in sessions) else None
    if not sessions:
        sessions = ["Off-peak"]

    return {
        "utc_time": now.strftime("%H:%M UTC"),
        "active_sessions": sessions,
        "overlap": overlap,
        "highest_liquidity": overlap is not None,
        "local_times": {
            "Jakarta (WIB)": now.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB"),
            "Tokyo": tokyo_now.strftime("%H:%M JST"),
            "London": london_now.strftime("%H:%M %Z"),
            "New_York": ny_now.strftime("%H:%M %Z"),
        },
        "recommendation": (
            "Highest volatility and liquidity — prefer breakout / trend continuation strategies"
            if overlap
            else f"Active {'/'.join(sessions)} session liquidity"
        ),
    }


async def handle_get_volatility_regime(args: dict, **ctx) -> dict:
    """Per-symbol volatility/regime classification (consumed by Stage2 prefetcher and specialist pipeline)."""
    session, _, settings = _get_macro_context(args, ctx)
    symbol = args.get("symbol", "")
    if not session:
        return {"error": "Database session required for get_volatility_regime"}
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    try:
        from monika.application.analysis.calculators.regime_classifier import classify_market_regime

        return await classify_market_regime(session, symbol, settings)
    except Exception as e:
        logger.warning(f"get_volatility_regime failed for {symbol}: {e}")
        return {"error": f"volatility regime calculation failed: {str(e)[:200]}"}


async def handle_get_macro_bias_score(args: dict, **ctx) -> dict:
    """Macro bias alignment score per symbol (consumed by Stage2 prefetcher)."""
    session, _, settings = _get_macro_context(args, ctx)
    symbol = args.get("symbol", "")
    direction = args.get("direction")
    if not session:
        return {"error": "Database session required for get_macro_bias_score"}
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    try:
        from monika.application.analysis.calculators.macro_bias_filter import evaluate_macro_alignment

        return await evaluate_macro_alignment(session, symbol, direction, settings)
    except Exception as e:
        logger.warning(f"get_macro_bias_score failed for {symbol}: {e}")
        return {"error": f"macro bias calculation failed: {str(e)[:200]}"}


async def handle_get_market_regime(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for get_market_regime"}

    symbols_input = args.get("symbols", [])
    if not symbols_input:
        single = args.get("symbol", "")
        if single:
            symbols_input = [single]

    symbols = symbols_input
    timeframe = args.get("timeframe", "D1")

    regimes = {}
    for symbol in symbols:
        adx_row = (
            await session.execute(
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == timeframe)
                .where(TechnicalIndicator.indicator_name == "ADX_14")
                .where(TechnicalIndicator.timestamp <= clock.now())
                .order_by(TechnicalIndicator.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if not adx_row:
            regimes[symbol] = {
                "regime": "unknown",
                "adx": None,
                "implication": (
                    "ADX data not available. This means technical indicators haven't been computed yet. "
                    "MANDATORY: Use conservative threshold of 9/14 for this cycle. "
                    "Do NOT enter BUY/SELL without exceptional confluence when regime is unknown."
                ),
            }
            continue

        try:
            adx_data = json.loads(adx_row.value_json)
            adx_val = adx_data.get("adx", 0) if isinstance(adx_data, dict) else float(adx_data)

            if adx_val > 40:
                regime = "strong_trend"
            elif adx_val > 25:
                regime = "trending"
            elif adx_val > 15:
                regime = "weak_trend"
            else:
                regime = "ranging"

            regimes[symbol] = {
                "regime": regime,
                "adx": round(adx_val, 1),
                "plus_di": adx_data.get("plus_di") if isinstance(adx_data, dict) else None,
                "minus_di": adx_data.get("minus_di") if isinstance(adx_data, dict) else None,
                "trend_direction": (
                    "bullish"
                    if isinstance(adx_data, dict) and adx_data.get("plus_di", 0) > adx_data.get("minus_di", 0)
                    else "bearish"
                )
                if adx_val > 20
                else "none",
                "implication": (
                    "Strong trend — prefer trend-following. Avoid counter-trend entries."
                    if adx_val > 35
                    else "Mild trend — SMC setups work well."
                    if adx_val > 20
                    else "Ranging market — be extra selective. FVG/OB entries prone to fake breakouts."
                ),
            }
        except Exception as e:
            regimes[symbol] = {"regime": "unknown", "error": str(e)}

    return {
        "timeframe": timeframe,
        "regimes": regimes,
        "trading_implication": (
            "Trending assets: confirm entry aligns with trend. "
            "Ranging assets: increase confluence threshold by +2 before trading."
        ),
    }
