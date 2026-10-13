# ==============================================================================
# File: analysis/tools/handlers/market_data/quotes_prices.py
# ==============================================================================

"""
Market quotes, price history, synthetic cross rates, spreads, and symbol specifications.
"""

import csv
import os
from datetime import timedelta, timezone
from typing import Any

from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.market_data.base import _get_session_and_symbol, logger
from monika.infrastructure.database.models import PriceOHLCV


async def handle_get_price_history(args: dict, **ctx) -> Any:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        watchlist = (settings or {}).get("trading", {}).get("watchlist") or ["XAUUSD"]
        symbol = watchlist[0] if watchlist else "XAUUSD"
    timeframe = args.get("timeframe", "H1")
    count = int(args.get("count") or args.get("limit") or 100)
    as_csv = args.get("format") == "csv" or args.get("as_csv") is True

    as_of_arg = args.get("as_of") or args.get("end_time") or args.get("before")
    as_of_dt = None
    if as_of_arg:
        try:
            import dateutil.parser as dparser

            as_of_dt = dparser.parse(str(as_of_arg).strip())
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)
        except Exception:
            as_of_dt = None

    rates = None
    if not as_of_dt:
        try:
            from monika.application.services.market_data_service import MarketDataService

            rates = await MarketDataService.ensure_bars(
                symbol=symbol, timeframe=timeframe, count=count, session=session
            )
            if rates and not as_csv:
                return rates
        except Exception as e:
            logger.debug(f"[{symbol}] ensure_bars unavailable: {e}")

    if as_csv and rates:
        lines = ["time,O,H,L,C,V"]
        for r in rates:
            if isinstance(r, dict):
                lines.append(
                    f"{r.get('time')},{r.get('open')},{r.get('high')},{r.get('low')},{r.get('close')},{r.get('tick_volume', r.get('volume', 0))}"
                )
        return "\n".join(lines)

    if session:
        query = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
        if as_of_dt:
            query = query.where(PriceOHLCV.timestamp <= as_of_dt)
        rows = (await session.execute(query.order_by(PriceOHLCV.timestamp.desc()).limit(count))).scalars().all()
        if rows:
            if as_csv:
                lines = ["time,O,H,L,C,V"]
                for r in reversed(rows):
                    t_str = (
                        r.timestamp.strftime("%m-%d %H:%M") if hasattr(r.timestamp, "strftime") else str(r.timestamp)
                    )
                    lines.append(f"{t_str},{r.open:.5f},{r.high:.5f},{r.low:.5f},{r.close:.5f},{r.volume}")
                return "\n".join(lines)
            return [
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
    return {"symbol": symbol, "timeframe": timeframe, "bars": [], "status": "no_data"}


async def handle_get_synthetic_cross_rate(args: dict, **ctx) -> dict:
    """
    Computes synthetic cross-rates, spread, and estimated volatility for cross pairs
    (e.g., GBPJPY = GBPUSD * USDJPY, EURGBP = EURUSD / GBPUSD, EURJPY = EURUSD * USDJPY).
    """
    _, symbol, _ = _get_session_and_symbol(args, ctx)
    cross_symbol = (
        str(args.get("pair") or args.get("cross_symbol") or args.get("symbol") or symbol or "")
        .upper()
        .replace("/", "")
        .strip()
    )
    if not cross_symbol:
        return {"error": "Missing required pair or cross_symbol parameter"}

    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

        client = get_mt5_client()
        live_tick = await client.get_latest_tick(cross_symbol)
        if live_tick and live_tick.get("bid"):
            return {
                "symbol": cross_symbol,
                "is_synthetic": False,
                "bid": live_tick.get("bid"),
                "ask": live_tick.get("ask"),
                "spread_pips": round(
                    (live_tick.get("ask", 0) - live_tick.get("bid", 0)) * (100 if "JPY" in cross_symbol else 10000), 2
                ),
                "source": "live_broker_tick",
            }
    except Exception:
        pass

    # Synthetic triangular calculations
    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

        client = get_mt5_client()
        eurusd = await client.get_latest_tick("EURUSD")
        gbpusd = await client.get_latest_tick("GBPUSD")
        usdjpy = await client.get_latest_tick("USDJPY")
        audusd = await client.get_latest_tick("AUDUSD")

        eur_price = (eurusd.get("bid", 1.0850) + eurusd.get("ask", 1.0850)) / 2 if eurusd else 1.0850
        gbp_price = (gbpusd.get("bid", 1.2950) + gbpusd.get("ask", 1.2950)) / 2 if gbpusd else 1.2950
        jpy_price = (usdjpy.get("bid", 152.00) + usdjpy.get("ask", 152.00)) / 2 if usdjpy else 152.00
        aud_price = (audusd.get("bid", 0.6550) + audusd.get("ask", 0.6550)) / 2 if audusd else 0.6550

        synth_rate = None
        formula = ""
        if cross_symbol in ("GBPJPY", "GBP_JPY"):
            synth_rate = gbp_price * jpy_price
            formula = "GBPUSD * USDJPY"
        elif cross_symbol in ("EURJPY", "EUR_JPY"):
            synth_rate = eur_price * jpy_price
            formula = "EURUSD * USDJPY"
        elif cross_symbol in ("AUDJPY", "AUD_JPY"):
            synth_rate = aud_price * jpy_price
            formula = "AUDUSD * USDJPY"
        elif cross_symbol in ("EURGBP", "EUR_GBP"):
            synth_rate = eur_price / gbp_price
            formula = "EURUSD / GBPUSD"
        elif cross_symbol in ("EURAUD", "EUR_AUD"):
            synth_rate = eur_price / aud_price
            formula = "EURUSD / AUDUSD"
        elif cross_symbol in ("GBPAUD", "GBP_AUD"):
            synth_rate = gbp_price / aud_price
            formula = "GBPUSD / AUDUSD"

        if synth_rate is not None:
            # Synthetic spread approximation (sum of percentage spreads)
            spread_pips = round(
                (0.00015 / eur_price + 0.015 / jpy_price) * synth_rate * (100 if "JPY" in cross_symbol else 10000), 1
            )
            # Estimated ATR approximation from typical 0.65% daily volatility
            est_daily_atr = round(synth_rate * 0.0065, 4 if "JPY" not in cross_symbol else 2)
            return {
                "symbol": cross_symbol,
                "is_synthetic": True,
                "synthetic_rate": round(synth_rate, 5 if "JPY" not in cross_symbol else 3),
                "spread_pips": spread_pips,
                "estimated_daily_atr": est_daily_atr,
                "formula": formula,
                "components": {
                    "eurusd": eur_price,
                    "gbpusd": gbp_price,
                    "usdjpy": jpy_price,
                    "audusd": aud_price,
                },
                "status": "success",
            }
    except Exception as e:
        logger.debug(f"Synthetic calculation error: {e}")

    return {
        "symbol": cross_symbol,
        "status": "unavailable",
        "message": f"Could not synthesize cross-rate for {cross_symbol}",
    }


async def handle_export_historical_data_csv(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    timeframe = str(args.get("timeframe", "H1")).upper()
    days_back = int(args.get("days_back", 30))
    limit = int(args.get("limit", 5000))

    since = clock.now() - timedelta(days=days_back)
    rows = []
    if session:
        rows = list(
            (
                await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == timeframe)
                    .where(PriceOHLCV.timestamp >= since)
                    .order_by(PriceOHLCV.timestamp.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    # Fallback to MT5 fetch if DB has insufficient data
    if len(rows) < 10:
        try:
            from monika.infrastructure.brokers.mt5_client import get_mt5_client

            client = get_mt5_client(settings)
            if client:
                mt5_candles = await client.get_ohlcv(symbol, timeframe, count=min(limit, 5000))
                if mt5_candles is not None and len(mt5_candles) > 0:
                    rows = mt5_candles
        except Exception:
            pass

    if len(rows) == 0:
        return {"error": f"No historical data available for {symbol} ({timeframe}) in the last {days_back} days."}

    export_dir = os.path.join(os.getcwd(), "data", "exports")
    os.makedirs(export_dir, exist_ok=True)
    clean_sym = symbol.replace("/", "")
    filename = args.get("output_filename") or f"{clean_sym}_{timeframe}_{days_back}d.csv"
    filepath = os.path.join(export_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for r in rows:
            if isinstance(r, dict):
                ts = r.get("time") or r.get("timestamp")
                writer.writerow([ts, r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume", 0)])
            else:
                ts = r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp)
                writer.writerow([ts, r.open, r.high, r.low, r.close, r.volume])

    executor = ctx.get("executor")
    if executor and hasattr(executor, "add_pending_file"):
        executor.add_pending_file(file_path=filepath, filename=filename, caption=f"OHLCV {symbol} ({timeframe})")

    return {
        "status": "success",
        "symbol": symbol,
        "timeframe": timeframe,
        "rows_exported": len(rows),
        "file_path": filepath,
        "days_back": days_back,
        "message": f"Exported {len(rows)} candles to {filepath}",
    }


async def handle_get_spread_snapshot(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    symbols = args.get("symbols")
    if not symbols:
        if symbol:
            symbols = [symbol]
        else:
            symbols = (
                (settings or {})
                .get("trading", {})
                .get("asset_universe", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"])
            )

    from monika.domain.risk.position_sizing import DEFAULT_INSTRUMENTS

    mt5_client = None
    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

        mt5_client = get_mt5_client(settings)
    except Exception:
        pass

    spreads = {}
    for sym in symbols:
        clean_sym = sym.strip().upper().replace("/", "")
        spec = DEFAULT_INSTRUMENTS.get(clean_sym)
        pip_size = spec.pip_size if spec else (0.01 if "JPY" in clean_sym or "XAU" in clean_sym else 0.0001)

        latest_bar = None
        if session:
            try:
                latest_bar = (
                    await session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == clean_sym)
                        .where(PriceOHLCV.timeframe == "M15")
                        .where(PriceOHLCV.timestamp <= clock.now())
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
            except Exception:
                pass

        typical_spread_pips = {
            "EURUSD": 1.0,
            "GBPUSD": 1.5,
            "USDJPY": 1.2,
            "AUDUSD": 1.4,
            "XAUUSD": 2.5,
            "BTCUSD": 15.0,
            "XTIUSD": 3.0,
        }.get(clean_sym, 2.0)

        current_spread_pips = typical_spread_pips
        status = "normal"
        last_price = latest_bar.close if latest_bar else None
        last_updated = (
            latest_bar.timestamp.isoformat()
            if latest_bar and hasattr(latest_bar.timestamp, "isoformat")
            else (str(latest_bar.timestamp) if latest_bar else None)
        )

        if mt5_client and hasattr(mt5_client, "get_current_price"):
            try:
                tick = await mt5_client.get_current_price(clean_sym)
                if tick and tick.get("bid") is not None and tick.get("ask") is not None:
                    bid = float(tick["bid"])
                    ask = float(tick["ask"])
                    diff = ask - bid
                    if pip_size > 0:
                        current_spread_pips = round(diff / pip_size, 1)
                    else:
                        current_spread_pips = round(diff, 1)
                    last_price = round((bid + ask) / 2, 5)
                    last_updated = clock.now().isoformat()
                    if current_spread_pips > typical_spread_pips * 2.0:
                        status = "elevated"
                    elif current_spread_pips > typical_spread_pips * 3.5:
                        status = "extreme"
            except Exception as tick_err:
                logger.debug(f"[{clean_sym}] Failed to fetch live tick spread: {tick_err}")

        spreads[clean_sym] = {
            "current_spread_pips": current_spread_pips,
            "typical_spread_pips": typical_spread_pips,
            "spread_status": status,
            "pip_size": pip_size,
            "last_price": last_price,
            "last_updated": last_updated,
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

    from monika.domain.risk.position_sizing import DEFAULT_INSTRUMENTS

    clean_sym = symbol.strip().upper().replace("/", "")
    spec = DEFAULT_INSTRUMENTS.get(clean_sym)
    pip_size = spec.pip_size if spec else (0.01 if "JPY" in clean_sym or "XAU" in clean_sym else 0.0001)

    # 1. Try fetching current live tick from MT5 if connected
    tick = None
    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

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
        ts_str = (
            ts.isoformat()
            if ts is not None and hasattr(ts, "isoformat")
            else (str(ts) if ts else clock.now().isoformat())
        )

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
            "EURUSD": 1.0,
            "GBPUSD": 1.5,
            "USDJPY": 1.2,
            "AUDUSD": 1.4,
            "XAUUSD": 2.5,
            "BTCUSD": 15.0,
            "XTIUSD": 3.0,
        }.get(clean_sym, 2.0)
        spread_amt = typical_spread_pips * pip_size
        bid = round(close_price - (spread_amt / 2), 5)
        ask = round(close_price + (spread_amt / 2), 5)
        ts_str = (
            latest_bar.timestamp.isoformat()
            if hasattr(latest_bar.timestamp, "isoformat")
            else str(latest_bar.timestamp)
        )

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
        "message": f"No live tick or historical OHLCV data found for {clean_sym}",
    }


async def handle_get_symbol_specification(args: dict, **ctx) -> dict:
    _, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    from monika.domain.market.instrument_identity import resolve_instrument_identity

    norm_sym = resolve_instrument_identity(symbol).canonical_symbol

    executor = ctx.get("executor")
    client = ctx.get("mt5_client") or ctx.get("client") or getattr(executor, "mt5_client", None)

    from monika.domain.risk.position_sizing import get_instrument_spec

    spec = get_instrument_spec(norm_sym, mt5_client=client)

    return {
        "symbol": norm_sym,
        "contract_size": spec.contract_size,
        "pip_size": spec.pip_size,
        "pip_value_usd": spec.pip_value_usd,
        "digits": spec.digits,
        "min_lot": getattr(spec, "min_lot", 0.01),
        "max_lot": getattr(spec, "max_lot", 100.0),
        "status": "success",
    }
