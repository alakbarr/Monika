# ==============================================================================
# File: analysis/tools/handlers/market_data/charts.py
# ==============================================================================

"""
Candlestick charts, SMC chart plotting, and equity curve visualizations.
"""

from datetime import timedelta

from sqlalchemy import desc, select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.market_data_handlers.base import _get_session_and_symbol, logger
from monika.infrastructure.database.models import (
    FVGZone,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
    SwingPoint,
)


async def handle_get_chart(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        watchlist = (settings or {}).get("trading", {}).get("watchlist") or ["XAUUSD"]
        symbol = watchlist[0] if watchlist else "XAUUSD"

    timeframe = args.get("timeframe", "H4")
    limit = min(max(args.get("candles", 80), 20), 200)

    rows = []
    if session:
        rows = (
            (
                await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == timeframe)
                    .where(PriceOHLCV.timestamp <= clock.now())
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    ohlcv_data = []
    if rows and len(rows) >= 5:
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
    else:
        try:
            from monika.application.services.market_data_service import MarketDataService

            bars = await MarketDataService.ensure_bars(symbol=symbol, timeframe=timeframe, count=limit, session=session)
            if bars and len(bars) >= 5:
                import dateutil.parser as dparser

                for b in bars:
                    ts = b.get("time")
                    if isinstance(ts, str):
                        try:
                            ts = dparser.parse(ts)
                        except Exception:
                            ts = clock.now()
                    ohlcv_data.append(
                        {
                            "timestamp": ts,
                            "open": float(b.get("open", 0.0)),
                            "high": float(b.get("high", 0.0)),
                            "low": float(b.get("low", 0.0)),
                            "close": float(b.get("close", 0.0)),
                            "volume": float(b.get("volume", 0.0)),
                        }
                    )
        except Exception as bar_err:
            logger.debug(f"[handle_get_chart] ensure_bars fallback error: {bar_err}")

    if not ohlcv_data or len(ohlcv_data) < 5:
        return {"error": f"Insufficient price history data for {symbol} {timeframe} to generate chart"}

    try:
        include_smc = args.get("smc", True)
        chart_buf = None
        if include_smc and session is not None:
            try:
                from monika.core.analytics.chart_generator import generate_smc_candlestick_chart

                fvg_rows = (
                    (
                        await session.execute(
                            select(FVGZone).where(FVGZone.symbol == symbol, FVGZone.timeframe == timeframe).limit(10)
                        )
                    )
                    .scalars()
                    .all()
                )
                swing_rows = (
                    (
                        await session.execute(
                            select(SwingPoint)
                            .where(SwingPoint.symbol == symbol, SwingPoint.timeframe == timeframe)
                            .order_by(desc(SwingPoint.timestamp))
                            .limit(10)
                        )
                    )
                    .scalars()
                    .all()
                )
                fvg_list = [
                    {
                        "top": float(getattr(f, "gap_high", getattr(f, "top", 0.0))),
                        "bottom": float(getattr(f, "gap_low", getattr(f, "bottom", 0.0))),
                        "type": getattr(f, "direction", getattr(f, "type", "bullish")),
                        "timestamp": getattr(f, "formed_at", getattr(f, "created_at", None)),
                    }
                    for f in fvg_rows
                ]
                swings_list = [{"price": float(s.price), "type": s.type, "timestamp": s.timestamp} for s in swing_rows]
                chart_buf, _ = generate_smc_candlestick_chart(
                    ohlcv_data,
                    symbol=symbol,
                    timeframe=timeframe,
                    fvg_list=fvg_list if fvg_list else None,
                    swing_points=swings_list if swings_list else None,
                    save_to_disk=False,
                )
            except Exception as smc_err:
                logger.debug(f"[handle_get_chart] SMC overlay render fallback: {smc_err}")

        if chart_buf is None:
            from monika.core.analytics.chart_generator import generate_candlestick_chart

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


async def handle_plot_price_chart(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = str(args.get("timeframe", "H1")).upper()
    candles_count = int(args.get("candles", 80))
    overlay_smc = args.get("overlay_smc", True)

    if not session:
        return {"error": "Database session required for plot_price_chart"}

    rows = (
        (
            await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(candles_count)
            )
        )
        .scalars()
        .all()
    )

    if not rows or len(rows) < 5:
        return {"error": f"Insufficient price history for {symbol} ({timeframe})"}

    ohlcv_data = [
        {
            "timestamp": r.timestamp,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume or 0,
        }
        for r in reversed(rows)
    ]

    fvg_list = []
    swing_points = []
    if overlay_smc:
        try:
            fvgs = (
                (
                    await session.execute(
                        select(FVGZone)
                        .where(FVGZone.symbol == symbol, FVGZone.timeframe == timeframe, FVGZone.filled_at.is_(None))
                        .order_by(FVGZone.formed_at.desc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            fvg_list = [{"top": f.gap_high, "bottom": f.gap_low, "type": f.direction} for f in fvgs]

            swings = (
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
            swing_points = [{"price": s.price, "type": s.type, "time": s.timestamp} for s in swings]
        except Exception as e:
            logger.debug(f"Failed fetching SMC overlays for chart: {e}")

    from monika.core.analytics.chart_generator import generate_smc_candlestick_chart

    try:
        buf, saved_path = generate_smc_candlestick_chart(
            ohlcv_data,
            symbol=symbol,
            timeframe=timeframe,
            fvg_list=fvg_list,
            swing_points=swing_points,
            save_to_disk=True,
        )
        chart_id = f"chart_{symbol}_{timeframe}_{int(clock.now().timestamp())}"
        executor = ctx.get("executor")
        if executor and hasattr(executor, "_pending_charts"):
            executor._pending_charts[chart_id] = buf

        return {
            "status": "success",
            "chart_id": chart_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles_rendered": len(rows),
            "file_path": saved_path,
            "fvg_boxes_rendered": len(fvg_list),
            "swing_markers_rendered": len(swing_points),
            "message": f"SMC chart rendered successfully and saved to {saved_path}",
        }
    except Exception as e:
        logger.error(f"Error plotting SMC chart for {symbol}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def handle_plot_equity_curve(args: dict, **ctx) -> dict:
    """Plot and deliver inline PNG equity curve chart with drawdown bands."""
    session, _, _ = _get_session_and_symbol(args, ctx)
    if not session:
        return {"error": "Database session required for plot_equity_curve"}

    days_back = int(args.get("days_back", 90))
    since = clock.now() - timedelta(days=days_back)

    from monika.core.analytics.chart_generator import generate_equity_curve_chart
    from monika.infrastructure.database.models import PaperTradeRecord, Position

    # Query closed trades
    records = []
    try:
        trades = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.closed_at >= since)
                    .order_by(PaperTradeRecord.closed_at.asc())
                )
            )
            .scalars()
            .all()
        )
        for t in trades:
            pnl = float(getattr(t, "realized_pnl", getattr(t, "pnl_usd", 0.0)) or 0.0)
            records.append(
                {
                    "time": t.closed_at,
                    "pnl": pnl,
                }
            )
    except Exception as e:
        logger.debug(f"PaperTradeRecord query error: {e}")

    if not records:
        try:
            positions = (
                (
                    await session.execute(
                        select(Position).where(Position.closed_at >= since).order_by(Position.closed_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            for p in positions:
                pnl = float(getattr(p, "realized_pnl", getattr(p, "pnl_usd", 0.0)) or 0.0)
                records.append(
                    {
                        "time": p.closed_at,
                        "pnl": pnl,
                    }
                )
        except Exception as e:
            logger.debug(f"Position query error: {e}")

    try:
        buf, saved_path = generate_equity_curve_chart(
            records, title="Monika Portfolio Performance & Drawdown", save_to_disk=True
        )
        chart_id = f"equity_curve_{int(clock.now().timestamp())}"
        executor = ctx.get("executor")
        if executor and hasattr(executor, "_pending_charts"):
            executor._pending_charts[chart_id] = buf

        return {
            "status": "success",
            "chart_id": chart_id,
            "trades_counted": len(records),
            "file_path": saved_path,
            "message": f"Equity curve rendered successfully ({len(records)} closed trades) and saved to {saved_path}",
        }
    except Exception as err:
        logger.error(f"Error plotting equity curve: {err}", exc_info=True)
        return {"status": "error", "error": str(err)}
