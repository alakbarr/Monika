# ==============================================================================
# File: analysis/tools/handlers/market_data/structures_smc.py
# ==============================================================================

"""
Market structure, swing points, structure breaks, SMC zones (OB, FVG), Fibonacci levels, and patterns.
"""

from sqlalchemy import desc, select

from monika.application.analysis.tools.handlers.market_data_handlers.base import _get_session_and_symbol, logger
from monika.infrastructure.database.models import (
    FVGZone,
    OrderBlock,
    PriceOHLCV,
    SRZone,
    StructureBreak,
    SwingPoint,
)


async def handle_get_swing_points(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"symbol": symbol, "timeframe": timeframe, "swing_points": []}

    rows = (
        (
            await session.execute(
                select(SwingPoint)
                .where(SwingPoint.symbol == symbol, SwingPoint.timeframe == timeframe)
                .order_by(SwingPoint.timestamp.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "swing_points": [
            {
                "type": r.type,
                "price": r.price,
                "timestamp": r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp),
            }
            for r in rows
        ],
    }


async def handle_get_structure_breaks(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"symbol": symbol, "timeframe": timeframe, "breaks": []}

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


async def handle_get_sr_zones(args: dict, **ctx) -> dict:
    """Standalone Support/Resistance zones query (referenced by OPERATOR_INTERACTIVE_TOOLS binding)."""
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"symbol": symbol, "timeframe": timeframe, "zones": []}

    rows = (
        (
            await session.execute(
                select(SRZone)
                .where(SRZone.symbol == symbol, SRZone.timeframe == timeframe)
                .order_by(desc(SRZone.strength))
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "zones": [
            {
                "price_high": r.price_high,
                "price_low": r.price_low,
                "strength": r.strength,
                "last_touched": r.last_touched.isoformat()
                if getattr(r, "last_touched", None) is not None and r.last_touched is not None
                else None,
            }
            for r in rows
        ],
    }


async def handle_get_smc_zones(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"symbol": symbol, "timeframe": timeframe, "status": "no_session"}

    sr_rows = (
        (await session.execute(select(SRZone).where(SRZone.symbol == symbol, SRZone.timeframe == timeframe).limit(10)))
        .scalars()
        .all()
    )
    ob_rows = (
        (
            await session.execute(
                select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe).limit(10)
            )
        )
        .scalars()
        .all()
    )
    fvg_rows = (
        (
            await session.execute(
                select(FVGZone).where(FVGZone.symbol == symbol, FVGZone.timeframe == timeframe).limit(10)
            )
        )
        .scalars()
        .all()
    )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "sr_zones": [{"price_high": r.price_high, "price_low": r.price_low, "strength": r.strength} for r in sr_rows],
        "order_blocks": [
            {
                "price_high": r.price_high,
                "price_low": r.price_low,
                "direction": getattr(r, "direction", "bullish"),
                "mitigated": bool(getattr(r, "mitigated_at", None)),
                "formed_at": r.formed_at.isoformat() if hasattr(r.formed_at, "isoformat") else str(r.formed_at),
            }
            for r in ob_rows
        ],
        "fvg_zones": [
            {
                "gap_high": r.gap_high,
                "gap_low": r.gap_low,
                "direction": getattr(r, "direction", "bullish"),
                "mitigated": bool(getattr(r, "mitigated_at", None)),
                "formed_at": r.formed_at.isoformat() if hasattr(r.formed_at, "isoformat") else str(r.formed_at),
            }
            for r in fvg_rows
        ],
        "total_order_blocks": len(ob_rows),
        "total_fvg_zones": len(fvg_rows),
    }


async def handle_get_fibonacci_levels(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    manual_high = args.get("high")
    manual_low = args.get("low")

    # Direct calculation if user provides manual high and low
    if manual_high is not None and manual_low is not None:
        try:
            high = float(manual_high)
            low = float(manual_low)
            if high <= low:
                return {"error": "Invalid bounds: high must be greater than low"}
            diff = high - low
            trend = args.get("trend", "bullish")
            if trend == "bullish":
                levels = {
                    "0.0 (Swing Low - Origin)": low,
                    "0.236": round(low + diff * 0.236, 4),
                    "0.382": round(low + diff * 0.382, 4),
                    "0.500 (Equilibrium)": round(low + diff * 0.500, 4),
                    "0.618 (Golden Pocket)": round(low + diff * 0.618, 4),
                    "0.705 (OTE)": round(low + diff * 0.705, 4),
                    "0.786": round(low + diff * 0.786, 4),
                    "1.0 (Swing High - Target)": high,
                    "1.272 (Extension)": round(low + diff * 1.272, 4),
                    "1.618 (Golden Extension)": round(low + diff * 1.618, 4),
                }
            else:
                levels = {
                    "0.0 (Swing High - Origin)": high,
                    "0.236": round(high - diff * 0.236, 4),
                    "0.382": round(high - diff * 0.382, 4),
                    "0.500 (Equilibrium)": round(high - diff * 0.500, 4),
                    "0.618 (Golden Pocket)": round(high - diff * 0.618, 4),
                    "0.705 (OTE)": round(high - diff * 0.705, 4),
                    "0.786": round(high - diff * 0.786, 4),
                    "1.0 (Swing Low - Target)": low,
                    "1.272 (Extension)": round(high - diff * 1.272, 4),
                    "1.618 (Golden Extension)": round(high - diff * 1.618, 4),
                }
            return {
                "source": "manual_input",
                "symbol": symbol or "CUSTOM",
                "trend": trend,
                "swing_high": high,
                "swing_low": low,
                "range": round(diff, 4),
                "levels": levels,
                "ote_zone": [levels["0.618 (Golden Pocket)"], levels["0.786"]],
                "discount_premium": {
                    "equilibrium": levels["0.500 (Equilibrium)"],
                    "discount_zone": [low, levels["0.500 (Equilibrium)"]]
                    if trend == "bullish"
                    else [levels["0.500 (Equilibrium)"], high],
                    "premium_zone": [levels["0.500 (Equilibrium)"], high]
                    if trend == "bullish"
                    else [low, levels["0.500 (Equilibrium)"]],
                },
            }
        except (ValueError, TypeError) as err:
            return {"error": f"Invalid high/low values: {err}"}

    if not symbol:
        return {"error": "Missing required parameter 'symbol' (or provide manual 'high' and 'low')"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"error": "Database session required for get_fibonacci_levels"}

    all_swings = (
        (
            await session.execute(
                select(SwingPoint)
                .where(SwingPoint.symbol == symbol)
                .where(SwingPoint.timeframe == timeframe)
                .order_by(SwingPoint.timestamp.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )

    if len(all_swings) < 2:
        return {"error": "Insufficient swing points to determine Fibonacci levels"}

    all_swings = sorted(all_swings, key=lambda s: s.timestamp)

    recent_subset = all_swings[-8:] if len(all_swings) > 8 else all_swings
    best_high = None
    best_low = None
    best_range = 0.0

    for i in range(len(recent_subset)):
        for j in range(i + 1, len(recent_subset)):
            s_a, s_b = recent_subset[i], recent_subset[j]
            if s_a.type != s_b.type:
                cur_h = s_a if s_a.type == "high" else s_b
                cur_l = s_a if s_a.type == "low" else s_b
                rng = cur_h.price - cur_l.price
                if rng > best_range:
                    best_range = rng
                    best_high = cur_h
                    best_low = cur_l

    if best_high and best_low and best_range > 0:
        swing_high = best_high
        swing_low = best_low
        coherent = True
    else:
        highs = [s for s in all_swings if s.type == "high"]
        lows = [s for s in all_swings if s.type == "low"]
        if not highs or not lows:
            return {"error": "Not enough swing points found"}
        swing_high = highs[-1]
        swing_low = lows[-1]
        coherent = False

    high = swing_high.price
    low = swing_low.price
    diff = high - low

    if diff <= 0:
        return {"error": "Invalid swing pair: high <= low"}

    last_swing = all_swings[-1]
    if last_swing.type == "high":
        trend = "bullish"
        levels = {
            "0.0 (Swing Low - Origin)": low,
            "0.236": low + diff * 0.236,
            "0.382": low + diff * 0.382,
            "0.5 (Equilibrium)": low + diff * 0.5,
            "0.618 (Golden Zone)": low + diff * 0.618,
            "0.705": low + diff * 0.705,
            "0.786 (OTE)": low + diff * 0.786,
            "1.0 (Swing High - End)": high,
            "1.272 (Target Ext 1)": low + diff * 1.272,
            "1.414 (Target Ext 2)": low + diff * 1.414,
            "1.618 (Golden Extension)": low + diff * 1.618,
            "2.0 (Full Expansion)": low + diff * 2.0,
        }
        retracement_zone = f"Golden zone (OTE): {round(low + diff * 0.618, 5)} - {round(low + diff * 0.786, 5)}"
    else:
        trend = "bearish"
        levels = {
            "0.0 (Swing High - Origin)": high,
            "0.236": high - diff * 0.236,
            "0.382": high - diff * 0.382,
            "0.5 (Equilibrium)": high - diff * 0.5,
            "0.618 (Golden Zone)": high - diff * 0.618,
            "0.705": high - diff * 0.705,
            "0.786 (OTE)": high - diff * 0.786,
            "1.0 (Swing Low - End)": low,
            "1.272 (Target Ext 1)": high - diff * 1.272,
            "1.414 (Target Ext 2)": high - diff * 1.414,
            "1.618 (Golden Extension)": high - diff * 1.618,
            "2.0 (Full Expansion)": high - diff * 2.0,
        }
        retracement_zone = f"Golden zone (OTE): {round(high - diff * 0.786, 5)} - {round(high - diff * 0.618, 5)}"

    # Calculate current price zone mapping (Premium vs Discount vs OTE)
    current_price = None
    if args.get("current_price"):
        try:
            current_price = float(args["current_price"])
        except Exception:
            pass
    if current_price is None and session:
        try:
            latest_bar = (
                await session.execute(
                    select(PriceOHLCV).where(PriceOHLCV.symbol == symbol).order_by(desc(PriceOHLCV.timestamp)).limit(1)
                )
            ).scalar_one_or_none()
            if latest_bar:
                current_price = float(latest_bar.close)
        except Exception:
            pass

    eq_price = round(low + diff * 0.5, 5)
    ote_min = round(low + diff * 0.618, 5) if trend == "bullish" else round(high - diff * 0.786, 5)
    ote_max = round(low + diff * 0.786, 5) if trend == "bullish" else round(high - diff * 0.618, 5)

    current_zone = "UNKNOWN"
    in_ote_zone = False
    if current_price is not None:
        if current_price > eq_price:
            current_zone = "PREMIUM"
        elif current_price < eq_price:
            current_zone = "DISCOUNT"
        else:
            current_zone = "EQUILIBRIUM"
        in_ote_zone = bool(min(ote_min, ote_max) <= current_price <= max(ote_min, ote_max))

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "trend_context": trend,
        "coherent_pair": coherent,
        "current_price": current_price,
        "equilibrium_price": eq_price,
        "current_zone": current_zone,
        "in_ote_zone": in_ote_zone,
        "ote_bounds": [min(ote_min, ote_max), max(ote_min, ote_max)],
        "swing_high": {
            "price": high,
            "timestamp": swing_high.timestamp.isoformat()
            if hasattr(swing_high.timestamp, "isoformat")
            else str(swing_high.timestamp),
        },
        "swing_low": {
            "price": low,
            "timestamp": swing_low.timestamp.isoformat()
            if hasattr(swing_low.timestamp, "isoformat")
            else str(swing_low.timestamp),
        },
        "move_size": round(diff, 5),
        "fib_levels": {k: round(v, 5) for k, v in levels.items()},
        "optimal_trade_entry_zone": retracement_zone,
        "interpretation": (
            f"Dealing Range: {low} - {high}. Equilibrium: {eq_price}. "
            f"Current market is in {current_zone} zone. "
            f"{'Price is actively inside the Optimal Trade Entry (OTE) 0.618-0.786 zone.' if in_ote_zone else 'Price is outside OTE zone.'}"
        ),
    }


async def handle_get_optimal_intraday_levels(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    direction = args.get("direction", "buy")
    entry_price = float(args.get("entry_price", 0.0))
    if not session or entry_price <= 0:
        return {"symbol": symbol, "direction": direction, "entry_price": entry_price, "levels": {}}

    try:
        from monika.application.analysis.calculators.intraday_level_optimizer import compute_optimal_levels

        return await compute_optimal_levels(session, symbol, direction, entry_price, settings)
    except Exception as e:
        logger.debug(f"[{symbol}] Optimal levels calculation fallback: {e}")
        return {"symbol": symbol, "direction": direction, "entry_price": entry_price, "levels": {}}


async def handle_detect_candlestick_patterns(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = str(args.get("timeframe", "H1")).upper()
    lookback = int(args.get("lookback", 10))

    candles = []
    if session:
        rows = (
            (
                await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(lookback + 5)
                )
            )
            .scalars()
            .all()
        )
        candles = [
            {
                "time": r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in reversed(rows)
        ]

    from monika.domain.indicators.candlestick_patterns import detect_candlestick_patterns

    res = detect_candlestick_patterns(candles, lookback=lookback)
    res["symbol"] = symbol
    res["timeframe"] = timeframe
    return res


async def handle_scan_chart_patterns(args: dict, **ctx) -> dict:
    """Scan for classical (Double Top/Bottom, H&S) and harmonic patterns (Gartley, Bat, Butterfly, Crab)."""
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        symbol = "XAUUSD"
    timeframe = args.get("timeframe", "H4")
    order = int(args.get("order", 5))

    from monika.application.services.market_data_service import MarketDataService

    bars = await MarketDataService.ensure_bars(symbol=symbol, timeframe=timeframe, count=120, session=session)
    if not bars or len(bars) < 25:
        return {"error": f"Insufficient bars ({len(bars) if bars else 0}) for chart pattern scanning"}

    import pandas as pd

    df = pd.DataFrame(bars)
    from monika.domain.indicators.chart_patterns import scan_all_chart_patterns

    res = scan_all_chart_patterns(df, order=order)
    res["symbol"] = symbol
    res["timeframe"] = timeframe
    return res
