# ==============================================================================
# File: analysis/tools/handlers/market_data/technicals.py
# ==============================================================================

"""
Technical indicators, ATR, momentum, multi-timeframe summaries, pivots, ichimoku, and divergences.
"""

import json

from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.market_data_handlers.base import _get_session_and_symbol, logger
from monika.infrastructure.database.models import (
    DXYData,
    PriceOHLCV,
    StructureBreak,
    SwingPoint,
    TechnicalIndicator,
)


async def handle_get_technical_indicators(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = args.get("timeframe", "H4")
    if session:
        try:
            from monika.application.services.technical_indicator_service import (
                TechnicalIndicatorService as TechnicalIndicatorCalculator,
            )

            calc = TechnicalIndicatorCalculator(session, settings)
            snapshot = await calc.get_snapshot(symbol, timeframe)
            if not snapshot:
                try:
                    await calc.compute_and_save(symbol, timeframe)
                    snapshot = await calc.get_snapshot(symbol, timeframe)
                except Exception as comp_err:
                    logger.debug(f"[{symbol}] On-the-fly indicator computation failed: {comp_err}")

            rsi_divergence = None
            macd_divergence = None
            try:
                from monika.domain.indicators.technical import detect_macd_divergence, detect_rsi_divergence

                df = await calc._load_ohlcv(symbol, timeframe)
                if df is not None and len(df) >= 20:
                    import pandas as pd
                    import ta.momentum as ta_momentum
                    import ta.trend as ta_trend

                    high_s = pd.Series(df["high"].astype(float))
                    low_s = pd.Series(df["low"].astype(float))
                    close_s = pd.Series(df["close"].astype(float))
                    rsi_s = ta_momentum.rsi(close_s, window=14)
                    rsi_divergence = detect_rsi_divergence(high_s, low_s, close_s, rsi_s)
                    macd_obj = ta_trend.MACD(close_s)
                    macd_divergence = detect_macd_divergence(
                        high_s, low_s, close_s, macd_obj.macd(), macd_obj.macd_diff()
                    )
            except Exception as div_err:
                logger.debug(f"[{symbol}] Divergence calculation notice: {div_err}")

            res = {"symbol": symbol, "timeframe": timeframe, "indicators": snapshot or {}}
            if rsi_divergence:
                res["rsi_divergence"] = rsi_divergence
            if macd_divergence:
                res["macd_divergence"] = macd_divergence
            return res
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
            from monika.application.services.technical_indicator_service import (
                TechnicalIndicatorService as TechnicalIndicatorCalculator,
            )

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
            row = (
                await session.execute(
                    select(TechnicalIndicator)
                    .where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.timeframe == timeframe)
                    .where(TechnicalIndicator.indicator_name == "ATR_14")
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row:
                val = json.loads(row.value_json) if isinstance(row.value_json, str) else row.value_json
                return {"symbol": symbol, "timeframe": timeframe, "period": period, "atr": val, "atr_14": val}
        except Exception:
            pass

    return {"symbol": symbol, "timeframe": timeframe, "period": period, "status": "unavailable"}


async def handle_get_daily_range_context(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"symbol": symbol, "status": "no_session"}

    lookback_days = args.get("lookback_days") or args.get("lookback")
    lookback_val = int(lookback_days) if lookback_days is not None else None

    try:
        from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context

        return await compute_daily_range_context(session, symbol, settings, lookback_days=lookback_val)
    except Exception as e:
        logger.debug(f"[{symbol}] Daily range context fallback: {e}")
        return {"symbol": symbol, "status": "available", "adr_context": {}}


async def handle_get_price_momentum(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = str(args.get("timeframe", "H4")).upper()
    if timeframe == "1D":
        timeframe = "H4"
    elif timeframe == "1H":
        timeframe = "H1"
    if symbol.upper() == "DXY" and timeframe == "D1":
        timeframe = "H4"
    lookback_bars = args.get("lookback_bars", 20)
    lookback_bars = min(max(lookback_bars, 2), 100)

    if not session:
        return {"error": "No database session available"}

    if symbol.upper() in ("DXY", "DXY_PROXY", "USDX"):
        rows = (
            (await session.execute(select(DXYData).order_by(DXYData.date.desc()).limit(lookback_bars + 1)))
            .scalars()
            .all()
        )
        if len(rows) < 2:
            return {"error": "Insufficient DXY data. Use get_dxy() for DXY trend analysis."}
        rows = list(reversed(rows))
        latest_close = rows[-1].close
        lookback_close = rows[0].close
        pct_change = (latest_close - lookback_close) / lookback_close * 100
        price_move = abs(latest_close - lookback_close)
        timeframe_note = f'NOTE: DXY data is DAILY only. Requested timeframe "{timeframe}" not applicable. Using D1 equivalent with {len(rows) - 1} trading days.'
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
                3 if abs(pct_change) > 2.0 else 2 if abs(pct_change) > 1.0 else 1 if abs(pct_change) > 0.5 else 0
            ),
            "priced_in_risk_from_momentum": (
                "high"
                if abs(pct_change) > 2.0
                else "moderate_high"
                if abs(pct_change) > 1.0
                else "moderate"
                if abs(pct_change) > 0.5
                else "low"
            ),
            "interpretation": (
                f"DXY moved {abs(pct_change):.2f}% over last {len(rows) - 1} trading days. "
                f"{'USD strengthening — bearish for gold and EUR/GBP/AUD, bullish for USDJPY.' if pct_change > 0 else 'USD weakening — bullish for gold and EUR/GBP/AUD, bearish for USDJPY.'}"
            ),
        }

    rows = (
        (
            await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == timeframe)
                .where(PriceOHLCV.timestamp <= clock.now())
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(lookback_bars + 1)
            )
        )
        .scalars()
        .all()
    )

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
    except TypeError, ValueError:
        latest_close = 0.0
        lookback_close = 0.0
        pct_change = 0.0
        price_move = 0.0
    latest_time = rows[-1].timestamp
    lookback_time = rows[0].timestamp

    atr_row = (
        await session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.indicator_name == "ATR_14")
            .where(TechnicalIndicator.timestamp <= clock.now())
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    atr_value = None
    run_up_vs_atr = None
    if atr_row:
        try:
            raw_atr = (
                json.loads(atr_row.value_json)
                if isinstance(getattr(atr_row, "value_json", None), str)
                else getattr(atr_row, "value_json", None)
            )
            if raw_atr is not None:
                atr_value = float(raw_atr)
                if atr_value > 0:
                    run_up_vs_atr = round(price_move / atr_value, 2)
        except ValueError, TypeError:
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

    raw_tfs = args.get("timeframes") or args.get("timeframe")
    if isinstance(raw_tfs, str):
        timeframes = [t.strip().upper() for t in raw_tfs.split(",") if t.strip()]
    elif isinstance(raw_tfs, list):
        timeframes = [str(t).strip().upper() for t in raw_tfs if str(t).strip()]
    else:
        timeframes = ["M15", "H1", "H4", "D1"]

    mtf_data = {}

    if session:
        from monika.application.services.technical_indicator_service import (
            TechnicalIndicatorService as TechnicalIndicatorCalculator,
        )

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
                adx_row = (
                    await session.execute(
                        select(TechnicalIndicator)
                        .where(TechnicalIndicator.symbol == symbol)
                        .where(TechnicalIndicator.timeframe == tf)
                        .where(TechnicalIndicator.indicator_name == "ADX_14")
                        .where(TechnicalIndicator.timestamp <= clock.now())
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                if adx_row:
                    adx_data = (
                        json.loads(adx_row.value_json) if isinstance(adx_row.value_json, str) else adx_row.value_json
                    )
                    adx_val = adx_data.get("adx", 0) if isinstance(adx_data, dict) else float(adx_data)
                    regime = (
                        "strong_trend"
                        if adx_val > 40
                        else "trending"
                        if adx_val > 25
                        else "weak_trend"
                        if adx_val > 15
                        else "ranging"
                    )
            except Exception:
                pass

            # 3. Latest Swing High & Low
            recent_swings = []
            try:
                swings = (
                    (
                        await session.execute(
                            select(SwingPoint)
                            .where(SwingPoint.symbol == symbol)
                            .where(SwingPoint.timeframe == tf)
                            .order_by(SwingPoint.timestamp.desc())
                            .limit(4)
                        )
                    )
                    .scalars()
                    .all()
                )
                recent_swings = [
                    {
                        "type": s.type,
                        "price": s.price,
                        "time": s.timestamp.strftime("%Y-%m-%d %H:%M")
                        if hasattr(s.timestamp, "strftime")
                        else str(s.timestamp),
                    }
                    for s in swings
                ]
            except Exception:
                pass

            # 4. Latest Structure Breaks (BOS / ChoCH)
            recent_breaks = []
            try:
                breaks = (
                    (
                        await session.execute(
                            select(StructureBreak)
                            .where(StructureBreak.symbol == symbol)
                            .where(StructureBreak.timeframe == tf)
                            .order_by(StructureBreak.formed_at.desc())
                            .limit(2)
                        )
                    )
                    .scalars()
                    .all()
                )
                recent_breaks = [
                    {
                        "type": b.type,
                        "direction": b.direction,
                        "price": b.price,
                        "time": b.formed_at.strftime("%Y-%m-%d %H:%M")
                        if hasattr(b.formed_at, "strftime")
                        else str(b.formed_at),
                    }
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
        "usage_tip": "Check D1 for macro bias, H4 for structural trend, H1 for entry zone alignment.",
    }


async def handle_get_pivot_points(args: dict, **ctx) -> dict:
    """Calculate Pivot Points (Classic, Camarilla, or Woodie) for a symbol."""
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        symbol = "XAUUSD"
    method = args.get("method", "classic")
    timeframe = args.get("timeframe", "D1")

    from monika.application.services.market_data_service import MarketDataService

    bars = await MarketDataService.ensure_bars(symbol=symbol, timeframe=timeframe, count=5, session=session)
    if not bars or len(bars) < 2:
        return {"error": f"Insufficient historical bars for {symbol} to calculate pivot points"}

    prev_bar = bars[-2]
    high = float(prev_bar.get("high", 0.0))
    low = float(prev_bar.get("low", 0.0))
    close = float(prev_bar.get("close", 0.0))
    cur_price = float(bars[-1].get("close", close))

    from monika.domain.indicators.technical import compute_pivot_points

    levels = compute_pivot_points(high=high, low=low, close=close, method=method)
    levels["symbol"] = symbol
    levels["timeframe"] = timeframe
    levels["current_price"] = cur_price
    levels["status"] = "success"
    return levels


async def handle_get_ichimoku(args: dict, **ctx) -> dict:
    """Calculate Ichimoku Kinko Hyo cloud and signal status."""
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        symbol = "XAUUSD"
    timeframe = args.get("timeframe", "H4")

    from monika.application.services.market_data_service import MarketDataService

    bars = await MarketDataService.ensure_bars(symbol=symbol, timeframe=timeframe, count=100, session=session)
    if not bars or len(bars) < 52:
        return {"error": f"Insufficient bars ({len(bars) if bars else 0}) for Ichimoku (need >= 52)"}

    import pandas as pd

    df = pd.DataFrame(bars)
    from monika.domain.indicators.technical import compute_ichimoku

    res = compute_ichimoku(df)
    res["symbol"] = symbol
    res["timeframe"] = timeframe
    res["status"] = "success"
    return res


async def handle_get_seasonality(args: dict, **ctx) -> dict:
    """Calculate monthly and day-of-week calendar seasonality tendencies for a symbol."""
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        symbol = "XAUUSD"
    mode = args.get("type", "all").lower()

    from monika.application.services.market_data_service import MarketDataService

    bars = await MarketDataService.ensure_bars(symbol=symbol, timeframe="D1", count=750, session=session)
    if not bars or len(bars) < 30:
        return {"error": f"Insufficient daily data ({len(bars) if bars else 0}) for seasonality analysis"}

    import pandas as pd

    df = pd.DataFrame(bars)
    from monika.application.analysis.calculators.seasonality import SeasonalityCalculator

    out = {"symbol": symbol, "status": "success"}
    if mode in ("monthly", "all"):
        m_res = SeasonalityCalculator.compute_monthly_seasonality(df)
        out.update(m_res)
    if mode in ("day_of_week", "dow", "daily", "all"):
        d_res = SeasonalityCalculator.compute_day_of_week_seasonality(df)
        out.update(d_res)
    return out


async def handle_get_divergences(args: dict, **ctx) -> dict:
    """Scan for multi-timeframe RSI and MACD divergences."""
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        symbol = "XAUUSD"
    tfs = args.get("timeframes") or ["H1", "H4"]
    if isinstance(tfs, str):
        tfs = [t.strip().upper() for t in tfs.split(",") if t.strip()]

    import pandas as pd

    from monika.application.services.market_data_service import MarketDataService
    from monika.domain.indicators.technical import detect_macd_divergence, detect_rsi_divergence

    results = {}
    for tf in tfs:
        bars = await MarketDataService.ensure_bars(symbol=symbol, timeframe=tf, count=60, session=session)
        if not bars or len(bars) < 25:
            results[tf] = {"status": "insufficient_data"}
            continue
        df = pd.DataFrame(bars)

        import ta.momentum as ta_momentum
        import ta.trend as ta_trend

        high_s = pd.Series(df["high"].astype(float))
        low_s = pd.Series(df["low"].astype(float))
        close_s = pd.Series(df["close"].astype(float))

        rsi_s = ta_momentum.rsi(close_s, window=14)
        rsi_div = detect_rsi_divergence(high_s, low_s, close_s, rsi_s)

        m_calc = ta_trend.MACD(close_s)
        m_line = m_calc.macd()
        m_hist = m_calc.macd_diff()
        macd_div = detect_macd_divergence(high_s, low_s, close_s, macd_line=m_line, macd_hist=m_hist)

        results[tf] = {
            "rsi_divergence": rsi_div,
            "macd_divergence": macd_div,
            "has_confluence": (
                rsi_div.get("divergence") == macd_div.get("divergence") and rsi_div.get("divergence") != "none"
            ),
        }

    return {
        "symbol": symbol,
        "timeframes_analyzed": tfs,
        "results": results,
        "status": "success",
    }
