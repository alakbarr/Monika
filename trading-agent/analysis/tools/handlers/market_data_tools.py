"""
Market data tool handlers and self-registration.
Handles price history, technical indicators, ATR, structure breaks, swing points, Fibonacci, and intraday levels.
Direct execution without circular trampolines.
"""

import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.models import PriceOHLCV, TechnicalIndicator, SwingPoint, StructureBreak, SRZone, OrderBlock, FVGZone, DXYData
from analysis.tools.registry import ToolRegistry, ToolDefinition

logger = logging.getLogger("TradingAgent.Tools.MarketData")


def _get_session_and_symbol(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], Optional[str], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    if not sym:
        sym = args.get("symbol") or getattr(executor, "symbol", None)
    if sym and isinstance(sym, str):
        sym = sym.strip().upper().replace("/", "")
    return session, sym, settings


async def handle_get_price_history(args: dict, **ctx) -> Any:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    count = int(args.get("count", 100))

    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        rates = await client.get_rates(symbol=symbol, timeframe=timeframe, count=count)
        if rates:
            return rates
    except Exception as e:
        logger.debug(f"[{symbol}] MT5 get_rates unavailable: {e}")

    if session:
        rows = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(count)
        )).scalars().all()
        return [
            {
                "time": r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp),
                "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume
            }
            for r in reversed(rows)
        ]
    return {"symbol": symbol, "timeframe": timeframe, "bars": [], "status": "no_data"}


async def handle_get_technical_indicators(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if session:
        try:
            from indicators.technical import TechnicalIndicatorCalculator
            calc = TechnicalIndicatorCalculator(session, settings)
            snapshot = await calc.get_snapshot(symbol, timeframe)
            return {"symbol": symbol, "timeframe": timeframe, "indicators": snapshot or {}}
        except Exception as e:
            logger.debug(f"[{symbol}] Technical indicator snapshot calculation error: {e}")
    return {"symbol": symbol, "timeframe": timeframe, "indicators": {}, "status": "no_session"}


async def handle_get_atr(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    period = int(args.get("period", 14))

    if session:
        try:
            from indicators.technical import TechnicalIndicatorCalculator
            calc = TechnicalIndicatorCalculator(session, settings)
            snapshot = await calc.get_snapshot(symbol, timeframe)
            atr_val = (snapshot.get("ATR", {}) or {}).get("value") if snapshot else None
            if atr_val is not None:
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "period": period,
                    "atr": atr_val,
                    "atr_14": atr_val,
                }
        except Exception as e:
            logger.debug(f"[{symbol}] ATR calculation error: {e}")

        # Fallback to direct DB query on TechnicalIndicator
        try:
            row = (await session.execute(
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == timeframe)
                .where(TechnicalIndicator.indicator_name == "ATR_14")
                .order_by(TechnicalIndicator.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            if row:
                val = json.loads(row.value_json) if isinstance(row.value_json, str) else row.value_json
                return {"symbol": symbol, "timeframe": timeframe, "period": period, "atr": val, "atr_14": val}
        except Exception:
            pass

    return {"symbol": symbol, "timeframe": timeframe, "period": period, "status": "unavailable"}


async def handle_get_swing_points(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"symbol": symbol, "timeframe": timeframe, "swing_points": []}

    rows = (await session.execute(
        select(SwingPoint)
        .where(SwingPoint.symbol == symbol, SwingPoint.timeframe == timeframe)
        .order_by(SwingPoint.timestamp.desc())
        .limit(10)
    )).scalars().all()
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

    breaks = (await session.execute(
        select(StructureBreak)
        .where(StructureBreak.symbol == symbol, StructureBreak.timeframe == timeframe)
        .order_by(StructureBreak.formed_at.desc())
        .limit(5)
    )).scalars().all()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "breaks": [
            {
                "type": b.type,
                "broken_price": getattr(b, "broken_price", None),
                "formed_at": b.formed_at.isoformat() if hasattr(b.formed_at, "isoformat") else str(b.formed_at),
            }
            for b in breaks
        ],
    }


async def handle_get_sr_zones(args: dict, **ctx) -> dict:
    """Standalone Support/Resistance zones query (referenced by TELEGRAM_TOOLS binding)."""
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"symbol": symbol, "timeframe": timeframe, "zones": []}

    rows = (await session.execute(
        select(SRZone)
        .where(SRZone.symbol == symbol, SRZone.timeframe == timeframe)
        .order_by(desc(SRZone.strength))
        .limit(10)
    )).scalars().all()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "zones": [
            {
                "price_high": r.price_high,
                "price_low": r.price_low,
                "strength": r.strength,
                "last_touched": r.last_touched.isoformat() if getattr(r, "last_touched", None) is not None and r.last_touched is not None else None,
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

    sr_rows = (await session.execute(
        select(SRZone).where(SRZone.symbol == symbol, SRZone.timeframe == timeframe).limit(10)
    )).scalars().all()
    ob_rows = (await session.execute(
        select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe).limit(10)
    )).scalars().all()
    fvg_rows = (await session.execute(
        select(FVGZone).where(FVGZone.symbol == symbol, FVGZone.timeframe == timeframe).limit(10)
    )).scalars().all()

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "sr_zones": [
            {"price_high": r.price_high, "price_low": r.price_low, "strength": r.strength}
            for r in sr_rows
        ],
        "order_blocks": len(ob_rows),
        "fvg_zones": len(fvg_rows),
    }


async def handle_get_fibonacci_levels(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if not session:
        return {"error": "Database session required for get_fibonacci_levels"}

    all_swings = (await session.execute(
        select(SwingPoint)
        .where(SwingPoint.symbol == symbol)
        .where(SwingPoint.timeframe == timeframe)
        .order_by(SwingPoint.timestamp.desc())
        .limit(20)
    )).scalars().all()

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
        }
        retracement_zone = f"Golden zone (OTE): {round(high - diff * 0.786, 5)} - {round(high - diff * 0.618, 5)}"

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "trend_context": trend,
        "coherent_pair": coherent,
        "swing_high": {"price": high, "timestamp": swing_high.timestamp.isoformat() if hasattr(swing_high.timestamp, "isoformat") else str(swing_high.timestamp)},
        "swing_low": {"price": low, "timestamp": swing_low.timestamp.isoformat() if hasattr(swing_low.timestamp, "isoformat") else str(swing_low.timestamp)},
        "move_size": round(diff, 5),
        "fib_levels": {k: round(v, 5) for k, v in levels.items()},
        "optimal_trade_entry_zone": retracement_zone,
        "interpretation": (
            f"Draw Fibonacci from {trend} move. "
            f"{'Coherent swing pair used.' if coherent else 'WARNING: Fallback to independent swings — check manually.'} "
            f"Entry in 0.618-0.786 zone (OTE) offers highest-probability reversal."
        )
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
        from analysis.calculators.intraday_level_optimizer import compute_optimal_levels
        return await compute_optimal_levels(session, symbol, direction, entry_price, settings)
    except Exception as e:
        logger.debug(f"[{symbol}] Optimal levels calculation fallback: {e}")
        return {"symbol": symbol, "direction": direction, "entry_price": entry_price, "levels": {}}


async def handle_get_daily_range_context(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"symbol": symbol, "status": "no_session"}

    try:
        from analysis.calculators.daily_range_calculator import compute_daily_range_context
        return await compute_daily_range_context(session, symbol, settings)
    except Exception as e:
        logger.debug(f"[{symbol}] Daily range context fallback: {e}")
        return {"symbol": symbol, "status": "available", "adr_context": {}}


async def handle_get_price_momentum(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = str(args.get("timeframe", "H4")).upper()
    if timeframe == '1D':
        timeframe = 'H4'
    elif timeframe == '1H':
        timeframe = 'H1'
    if symbol.upper() == 'DXY' and timeframe == 'D1':
        timeframe = 'H4'
    lookback_bars = args.get("lookback_bars", 20)
    lookback_bars = min(max(lookback_bars, 2), 100)

    if not session:
        return {"error": "No database session available"}

    if symbol.upper() in ("DXY", "DXY_PROXY", "USDX"):
        rows = (await session.execute(
            select(DXYData)
            .order_by(DXYData.date.desc())
            .limit(lookback_bars + 1)
        )).scalars().all()
        if len(rows) < 2:
            return {"error": "Insufficient DXY data. Use get_dxy() for DXY trend analysis."}
        rows = list(reversed(rows))
        latest_close = rows[-1].close
        lookback_close = rows[0].close
        pct_change = (latest_close - lookback_close) / lookback_close * 100
        price_move = abs(latest_close - lookback_close)
        timeframe_note = f'NOTE: DXY data is DAILY only. Requested timeframe "{timeframe}" not applicable. Using D1 equivalent with {len(rows)-1} trading days.'
        return {
            "symbol": "DXY",
            "timeframe": "D1 (DAILY ONLY - yFinance source)",
            "timeframe_requested": timeframe,
            "timeframe_note": timeframe_note,
            "lookback_bars_available": len(rows) - 1,
            "lookback_price": round(lookback_close, 3),
            "current_price": round(latest_close, 3),
            "pct_change": round(pct_change, 4),
            "price_move_absolute": round(price_move, 3),
            "direction": "bullish" if pct_change > 0 else ("bearish" if pct_change < 0 else "flat"),
            "note": "DXY direct from Yahoo Finance daily data. Use run_up_vs_atr N/A for DXY.",
            "run_up_vs_atr": None,
            "momentum_score_for_priced_in": (
                3 if abs(pct_change) > 2.0 else
                2 if abs(pct_change) > 1.0 else
                1 if abs(pct_change) > 0.5 else 0
            ),
            "priced_in_risk_from_momentum": (
                "high" if abs(pct_change) > 2.0 else
                "moderate_high" if abs(pct_change) > 1.0 else
                "moderate" if abs(pct_change) > 0.5 else "low"
            ),
            "interpretation": (
                f"DXY moved {abs(pct_change):.2f}% over last {len(rows)-1} trading days. "
                f"{'USD strengthening — bearish for gold and EUR/GBP/AUD, bullish for USDJPY.' if pct_change > 0 else 'USD weakening — bullish for gold and EUR/GBP/AUD, bearish for USDJPY.'}"
            ),
        }

    rows = (await session.execute(
        select(PriceOHLCV)
        .where(PriceOHLCV.symbol == symbol)
        .where(PriceOHLCV.timeframe == timeframe)
        .where(PriceOHLCV.timestamp <= clock.now())
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(lookback_bars + 1)
    )).scalars().all()

    if len(rows) < 2:
        return {
            "error": (
                f"Insufficient price data for {symbol}/{timeframe}. "
                f"Need at least 2 bars, have {len(rows)}. "
                "Run price fetcher first."
            )
        }

    rows = list(reversed(rows))
    try:
        latest_close = float(rows[-1].close)
        lookback_close = float(rows[0].close)
        pct_change = (latest_close - lookback_close) / lookback_close * 100 if lookback_close else 0.0
        price_move = abs(latest_close - lookback_close)
    except (TypeError, ValueError):
        latest_close = 0.0
        lookback_close = 0.0
        pct_change = 0.0
        price_move = 0.0
    latest_time = rows[-1].timestamp
    lookback_time = rows[0].timestamp

    atr_row = (await session.execute(
        select(TechnicalIndicator)
        .where(TechnicalIndicator.symbol == symbol)
        .where(TechnicalIndicator.timeframe == timeframe)
        .where(TechnicalIndicator.indicator_name == "ATR_14")
        .where(TechnicalIndicator.timestamp <= clock.now())
        .order_by(TechnicalIndicator.timestamp.desc())
        .limit(1)
    )).scalar_one_or_none()

    atr_value = None
    run_up_vs_atr = None
    if atr_row:
        try:
            raw_atr = json.loads(atr_row.value_json) if isinstance(getattr(atr_row, 'value_json', None), str) else getattr(atr_row, 'value_json', None)
            if raw_atr is not None:
                atr_value = float(raw_atr)
                if atr_value > 0:
                    run_up_vs_atr = round(price_move / atr_value, 2)
        except (ValueError, TypeError):
            atr_value = None
            run_up_vs_atr = None

    if run_up_vs_atr is not None and isinstance(run_up_vs_atr, (int, float)):
        if run_up_vs_atr > 4.0:
            momentum_score = 3
            priced_in_risk = "high"
        elif run_up_vs_atr > 2.5:
            momentum_score = 2
            priced_in_risk = "moderate_high"
        elif run_up_vs_atr > 1.5:
            momentum_score = 1
            priced_in_risk = "moderate"
        else:
            momentum_score = 0
            priced_in_risk = "low"
    else:
        momentum_score = None
        priced_in_risk = "unknown_no_atr"

    bars_available = len(rows) - 1

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "lookback_bars_requested": lookback_bars,
        "lookback_bars_available": bars_available,
        "lookback_from": lookback_time.isoformat(),
        "lookback_to": latest_time.isoformat(),
        "lookback_price": round(lookback_close, 5),
        "current_price": round(latest_close, 5),
        "pct_change": round(pct_change, 4),
        "price_move_absolute": round(price_move, 5),
        "direction": "bullish" if pct_change > 0 else ("bearish" if pct_change < 0 else "flat"),
        "atr_14": round(atr_value, 5) if atr_value else None,
        "run_up_vs_atr": run_up_vs_atr,
        "momentum_score_for_priced_in": momentum_score,
        "priced_in_risk_from_momentum": priced_in_risk,
        "interpretation": (
            f"{symbol} moved {abs(pct_change):.2f}% ({price_move:.5f} points) "
            f"over last {bars_available} {timeframe} bars. "
            f"{'Run-up = ' + str(run_up_vs_atr) + 'x ATR_14 -> ' + priced_in_risk + ' priced-in momentum risk.' if run_up_vs_atr is not None else 'ATR unavailable for run-up ratio.'}"
        ),
    }


async def handle_get_multi_timeframe_summary(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}

    timeframes = ["H1", "H4", "D1"]
    mtf_data = {}

    if session:
        from indicators.technical import TechnicalIndicatorCalculator
        calc = TechnicalIndicatorCalculator(session, settings or {})

        for tf in timeframes:
            # 1. Technical Indicators Snapshot
            snapshot = {}
            try:
                snapshot = await calc.get_snapshot(symbol, tf) or {}
            except Exception as e:
                logger.debug(f"[{symbol}/{tf}] get_snapshot error: {e}")

            # Key indicators condensed
            condensed_indicators = {}
            if snapshot:
                for k in ["SMA_20", "SMA_50", "SMA_200", "EMA_20", "EMA_50", "RSI_14", "MACD_12_26_9", "ATR_14"]:
                    if k in snapshot:
                        condensed_indicators[k] = snapshot[k].get("value")

            # 2. ADX Market Regime
            regime = "unknown"
            adx_val = None
            try:
                adx_row = (await session.execute(
                    select(TechnicalIndicator)
                    .where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.timeframe == tf)
                    .where(TechnicalIndicator.indicator_name == "ADX_14")
                    .where(TechnicalIndicator.timestamp <= clock.now())
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if adx_row:
                    adx_data = json.loads(adx_row.value_json) if isinstance(adx_row.value_json, str) else adx_row.value_json
                    adx_val = adx_data.get("adx", 0) if isinstance(adx_data, dict) else float(adx_data)
                    regime = "strong_trend" if adx_val > 40 else "trending" if adx_val > 25 else "weak_trend" if adx_val > 15 else "ranging"
            except Exception:
                pass

            # 3. Latest Swing High & Low
            recent_swings = []
            try:
                swings = (await session.execute(
                    select(SwingPoint)
                    .where(SwingPoint.symbol == symbol)
                    .where(SwingPoint.timeframe == tf)
                    .order_by(SwingPoint.timestamp.desc())
                    .limit(4)
                )).scalars().all()
                recent_swings = [
                    {"type": s.type, "price": s.price, "time": s.timestamp.strftime("%Y-%m-%d %H:%M") if hasattr(s.timestamp, "strftime") else str(s.timestamp)}
                    for s in swings
                ]
            except Exception:
                pass

            # 4. Latest Structure Breaks (BOS / ChoCH)
            recent_breaks = []
            try:
                breaks = (await session.execute(
                    select(StructureBreak)
                    .where(StructureBreak.symbol == symbol)
                    .where(StructureBreak.timeframe == tf)
                    .order_by(StructureBreak.formed_at.desc())
                    .limit(2)
                )).scalars().all()
                recent_breaks = [
                    {"type": b.type, "direction": b.direction, "price": b.price, "time": b.formed_at.strftime("%Y-%m-%d %H:%M") if hasattr(b.formed_at, "strftime") else str(b.formed_at)}
                    for b in breaks
                ]
            except Exception:
                pass

            mtf_data[tf] = {
                "regime": regime,
                "adx_14": round(adx_val, 1) if adx_val is not None else None,
                "key_indicators": condensed_indicators,
                "recent_swings": recent_swings,
                "recent_structure_breaks": recent_breaks,
            }
    else:
        for tf in timeframes:
            mtf_data[tf] = {
                "regime": "unknown",
                "adx_14": None,
                "key_indicators": {},
                "recent_swings": [],
                "recent_structure_breaks": [],
            }

    h1_regime = mtf_data.get("H1", {}).get("regime")
    h4_regime = mtf_data.get("H4", {}).get("regime")
    d1_regime = mtf_data.get("D1", {}).get("regime")

    return {
        "symbol": symbol,
        "multi_timeframe": mtf_data,
        "regimes_summary": {"H1": h1_regime, "H4": h4_regime, "D1": d1_regime},
        "usage_tip": "Check D1 for macro bias, H4 for structural trend, H1 for entry zone alignment."
    }


async def handle_get_chart(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"error": "Database session required for get_chart"}

    timeframe = args.get("timeframe", "H4")
    limit = min(max(args.get("candles", 80), 20), 200)

    rows = (await session.execute(
        select(PriceOHLCV)
        .where(PriceOHLCV.symbol == symbol)
        .where(PriceOHLCV.timeframe == timeframe)
        .where(PriceOHLCV.timestamp <= clock.now())
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(limit)
    )).scalars().all()

    if not rows or len(rows) < 5:
        return {"error": f"Insufficient price history data for {symbol} {timeframe} to generate chart"}

    rows = list(reversed(rows))
    ohlcv_data = [
        {
            "timestamp": r.timestamp,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume or 0,
        }
        for r in rows
    ]

    from utils.chart_generator import generate_candlestick_chart
    try:
        chart_buf = generate_candlestick_chart(
            ohlcv_data, symbol=symbol, timeframe=timeframe, show_volume=True, show_ma=(20, 50)
        )
        chart_id = f"chart_{symbol}_{timeframe}_{int(clock.now().timestamp())}"
        executor = ctx.get("executor")
        if executor and hasattr(executor, "_pending_charts"):
            executor._pending_charts[chart_id] = chart_buf

        return {
            "chart_id": chart_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles_plotted": len(rows),
            "candles_rendered": len(rows),
            "status": "ready",
            "message": f"Candlestick chart for {symbol} ({timeframe}) with {len(rows)} candles generated and sent to user.",
        }
    except Exception as e:
        logger.error(f"Error generating chart for {symbol} {timeframe}: {e}")
        return {"error": f"Chart generation failed: {e}"}


async def handle_get_spread_snapshot(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    symbols = args.get("symbols")
    if not symbols:
        if symbol:
            symbols = [symbol]
        else:
            symbols = (settings or {}).get("trading", {}).get("asset_universe", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"])

    from risk.position_sizing import DEFAULT_INSTRUMENTS

    spreads = {}
    for sym in symbols:
        clean_sym = sym.strip().upper().replace('/', '')
        spec = DEFAULT_INSTRUMENTS.get(clean_sym)
        pip_size = spec.pip_size if spec else (0.01 if "JPY" in clean_sym or "XAU" in clean_sym else 0.0001)

        latest_bar = None
        if session:
            try:
                latest_bar = (await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == clean_sym)
                    .where(PriceOHLCV.timeframe == "M15")
                    .where(PriceOHLCV.timestamp <= clock.now())
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )).scalar_one_or_none()
            except Exception:
                pass

        typical_spread_pips = {
            "EURUSD": 1.0, "GBPUSD": 1.5, "USDJPY": 1.2,
            "AUDUSD": 1.4, "XAUUSD": 2.5, "BTCUSD": 15.0, "XTIUSD": 3.0
        }.get(clean_sym, 2.0)

        current_spread_pips = typical_spread_pips
        status = "normal"

        spreads[clean_sym] = {
            "current_spread_pips": current_spread_pips,
            "typical_spread_pips": typical_spread_pips,
            "spread_status": status,
            "pip_size": pip_size,
            "last_price": latest_bar.close if latest_bar else None,
            "last_updated": latest_bar.timestamp.isoformat() if latest_bar and hasattr(latest_bar.timestamp, "isoformat") else (str(latest_bar.timestamp) if latest_bar else None),
        }

    return {
        "timestamp": clock.now().isoformat(),
        "spreads": spreads,
        "universe_size": len(spreads),
    }


async def handle_get_market_quote(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}

    from risk.position_sizing import DEFAULT_INSTRUMENTS

    clean_sym = symbol.strip().upper().replace('/', '')
    spec = DEFAULT_INSTRUMENTS.get(clean_sym)
    pip_size = spec.pip_size if spec else (0.01 if "JPY" in clean_sym or "XAU" in clean_sym else 0.0001)

    # 1. Try fetching current live tick from MT5 if connected
    tick = None
    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client(settings)
        if hasattr(client, "get_current_price"):
            tick = await client.get_current_price(clean_sym)
    except Exception as e:
        logger.debug(f"[{clean_sym}] MT5 get_current_price unavailable: {e}")

    if tick and (tick.get("bid") is not None or tick.get("ask") is not None or tick.get("last") is not None):
        bid = float(tick["bid"]) if tick.get("bid") is not None else None
        ask = float(tick["ask"]) if tick.get("ask") is not None else None
        last = float(tick["last"]) if tick.get("last") is not None else None

        if bid is not None and ask is not None:
            price = round((bid + ask) / 2, 5)
            spread = round(ask - bid, 5)
            spread_pips = round(spread / pip_size, 1) if pip_size > 0 else round(spread, 1)
        elif last is not None:
            price = last
            spread = 0.0
            spread_pips = 0.0
        else:
            price = bid if bid is not None else ask
            spread = 0.0
            spread_pips = 0.0

        ts = tick.get("time")
        ts_str = ts.isoformat() if ts is not None and hasattr(ts, "isoformat") else (str(ts) if ts else clock.now().isoformat())

        return {
            "symbol": clean_sym,
            "price": price,
            "bid": bid if bid is not None else price,
            "ask": ask if ask is not None else price,
            "last_price": last if last is not None else price,
            "spread": spread,
            "spread_pips": spread_pips,
            "pip_size": pip_size,
            "timestamp": ts_str,
            "source": "mt5",
            "status": "success",
        }

    # 2. Fallback to latest PriceOHLCV in DB
    latest_bar = None
    if session:
        try:
            for tf in ["M15", "H1", "H4", "D1"]:
                res = await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == clean_sym, PriceOHLCV.timeframe == tf)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )
                latest_bar = res.scalar_one_or_none()
                if latest_bar:
                    break
        except Exception as e:
            logger.debug(f"[{clean_sym}] DB OHLCV fallback error: {e}")

    if latest_bar:
        close_price = float(latest_bar.close)
        typical_spread_pips = {
            "EURUSD": 1.0, "GBPUSD": 1.5, "USDJPY": 1.2,
            "AUDUSD": 1.4, "XAUUSD": 2.5, "BTCUSD": 15.0, "XTIUSD": 3.0
        }.get(clean_sym, 2.0)
        spread_amt = typical_spread_pips * pip_size
        bid = round(close_price - (spread_amt / 2), 5)
        ask = round(close_price + (spread_amt / 2), 5)
        ts_str = latest_bar.timestamp.isoformat() if hasattr(latest_bar.timestamp, "isoformat") else str(latest_bar.timestamp)

        return {
            "symbol": clean_sym,
            "price": close_price,
            "bid": bid,
            "ask": ask,
            "last_price": close_price,
            "high": float(latest_bar.high),
            "low": float(latest_bar.low),
            "open": float(latest_bar.open),
            "volume": float(latest_bar.volume or 0),
            "spread": round(spread_amt, 5),
            "spread_pips": typical_spread_pips,
            "pip_size": pip_size,
            "timestamp": ts_str,
            "timeframe": latest_bar.timeframe,
            "source": "db_ohlcv",
            "status": "success",
        }

    # 3. Fallback default if completely unavailable
    return {
        "symbol": clean_sym,
        "price": None,
        "bid": None,
        "ask": None,
        "last_price": None,
        "spread_pips": None,
        "timestamp": clock.now().isoformat(),
        "source": "unavailable",
        "status": "no_data",
        "message": f"No live tick or historical OHLCV data found for {clean_sym}"
    }


def register_market_data_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_market_quote",
            description="Fetch current market quote (live tick or latest price) for a symbol.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
            handler=handle_get_market_quote,
            toolset="market_data",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_multi_timeframe_summary",
            description="Composite multi-timeframe analysis across H1, H4, and D1.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_multi_timeframe_summary,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_chart",
            description="Generate candlestick chart image for visualization.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}, "candles": {"type": "integer"}}},
            handler=handle_get_chart,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_spread_snapshot",
            description="Fetch current spread snapshot for a symbol.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_spread_snapshot,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_price_history",
            description="Fetch OHLCV candlestick price history for a symbol and timeframe.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}, "count": {"type": "integer"}}},
            handler=handle_get_price_history,
            toolset="market_data",
            requires_db=True,
        ),

        ToolDefinition(
            name="get_technical_indicators",
            description="Fetch precalculated technical indicators (EMA, RSI, MACD, ATR, Bollinger, ADX).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_technical_indicators,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_atr",
            description="Fetch the Average True Range (ATR) indicator value for volatility assessment.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_atr,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_swing_points",
            description="Fetch recent high and low swing points for market structure analysis.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_swing_points,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_structure_breaks",
            description="Fetch recent Break of Structure (BOS) and Change of Character (CHoCH) events.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_structure_breaks,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_smc_zones",
            description="Fetch institutional Smart Money Concepts zones (Order Blocks, FVG, S/R).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_smc_zones,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_sr_zones",
            description="Fetch standalone Support/Resistance zones with strength ranking for a symbol and timeframe.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_sr_zones,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fibonacci_levels",
            description="Fetch Fibonacci retracement levels derived from recent swing points.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_fibonacci_levels,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_optimal_intraday_levels",
            description="Calculate optimal intraday entry, take-profit, and stop-loss levels.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "direction": {"type": "string"}, "entry_price": {"type": "number"}}},
            handler=handle_get_optimal_intraday_levels,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_daily_range_context",
            description="Fetch Average Daily Range (ADR) and current session range usage percentage.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_daily_range_context,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_price_momentum",
            description="Fetch momentum indicators including RSI and MACD.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_price_momentum,
            toolset="market_data",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)


register_market_data_tools()
