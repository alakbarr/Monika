# ==============================================================================
# File: services/market_data_service.py
# ==============================================================================

"""
Market Data Application Service.
Provides uniform access to symbol quotes, ticks, and liquidity status
abstracted from MT5 client or historical data providers, with automatic
cascade across MT5, Database cache, and Yahoo Finance.
"""

from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime, timezone
import logging

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from utils.infra.container import ServiceContainer, get_container
from utils.market.instrument_identity import resolve_instrument_identity

logger = logging.getLogger("TradingAgent.Services.MarketData")


def _to_yfinance_symbol(symbol: str) -> str:
    sym = symbol.strip().upper().replace("/", "")
    if sym.endswith(".JK") or "^" in sym or "=" in sym:
        return sym
    mapping = {
        "XAUUSD": "GC=F",
        "GOLD": "GC=F",
        "XTIUSD": "CL=F",
        "OIL": "CL=F",
        "WTI": "CL=F",
        "XBRUSD": "BZ=F",
        "BRENT": "BZ=F",
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "USTEC": "^IXIC",
        "NAS100": "^IXIC",
        "NASDAQ": "^IXIC",
        "US30": "^DJI",
        "DJI": "^DJI",
        "US500": "^GSPC",
        "SPX": "^GSPC",
        "USDIDR": "IDR=X",
    }
    if sym in mapping:
        return mapping[sym]
    if len(sym) == 6 and sym[:3] != sym[3:]:
        # Standard forex EURUSD -> EURUSD=X
        return f"{sym}=X"
    return sym


def _tf_to_yfinance_interval(tf: str) -> str:
    tf_upper = tf.upper()
    mapping = {
        "M1": "1m",
        "M5": "5m",
        "M15": "15m",
        "M30": "30m",
        "H1": "1h",
        "H4": "1h",
        "D1": "1d",
        "W1": "1wk",
        "MN1": "1mo",
    }
    return mapping.get(tf_upper, "1h")


class MarketDataService:
    """Service providing unified quote and market data access."""

    @staticmethod
    def get_latest_quote(
        symbol: str,
        container: Optional[ServiceContainer] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch current bid/ask quote for a symbol."""
        c = container or get_container()
        mt5_client = c.get("mt5_client")
        if not mt5_client:
            return None

        sym = symbol.upper()
        try:
            if hasattr(mt5_client, "get_quote"):
                return mt5_client.get_quote(sym)
            elif hasattr(mt5_client, "get_symbol_info_tick"):
                tick = mt5_client.get_symbol_info_tick(sym)
                if tick:
                    return {
                        "symbol": sym,
                        "bid": getattr(tick, "bid", 0.0),
                        "ask": getattr(tick, "ask", 0.0),
                        "spread": round((getattr(tick, "ask", 0.0) - getattr(tick, "bid", 0.0)), 5),
                    }
        except Exception as e:
            logger.debug(f"[MarketDataService] Quote fetch note for {sym}: {e}")
        return None

    @classmethod
    async def ensure_bars(
        cls,
        symbol: str,
        timeframe: str = "H1",
        count: int = 100,
        session: Optional[AsyncSession] = None,
        container: Optional[ServiceContainer] = None,
    ) -> List[Dict[str, Any]]:
        """
        Unified bar fetcher with cascade:
        1. MT5 client get_rates
        2. Database PriceOHLCV cache
        3. Yahoo Finance (yfinance) on-demand fallback (stocks, foreign pairs, unlisted instruments)
        """
        sym = symbol.strip().upper().replace("/", "")
        c = container or get_container()
        mt5_client = c.get("mt5_client")

        # 1. Try MT5
        if mt5_client:
            try:
                rates = await mt5_client.get_rates(symbol=sym, timeframe=timeframe, count=count)
                if rates and len(rates) > 0:
                    return rates
            except Exception as e:
                logger.debug(f"[MarketDataService] MT5 fetch failed for {sym}: {e}")

        # 2. Try Database Cache
        if session:
            try:
                from database.models import PriceOHLCV
                rows = (await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == sym, PriceOHLCV.timeframe == timeframe)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(count)
                )).scalars().all()
                if rows and len(rows) >= min(count, 30):
                    return [
                        {
                            "time": r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp),
                            "open": float(r.open),
                            "high": float(r.high),
                            "low": float(r.low),
                            "close": float(r.close),
                            "volume": float(r.volume),
                            "tick_volume": float(r.volume),
                        }
                        for r in reversed(rows)
                    ]
            except Exception as db_err:
                logger.debug(f"[MarketDataService] DB fetch failed for {sym}: {db_err}")

        # 3. Try yfinance fallback (runs in executor to avoid blocking event loop)
        try:
            import yfinance as yf
            import pandas as pd

            yf_symbol = _to_yfinance_symbol(sym)
            interval = _tf_to_yfinance_interval(timeframe)
            period = "1mo" if interval in ("1m", "5m", "15m", "30m", "1h") else "1y"

            def _fetch_yf():
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(period=period, interval=interval)
                return df

            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, _fetch_yf)

            if df is not None and not df.empty:
                df = df.tail(count)
                bars = []
                for idx, row in df.iterrows():
                    ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                        ts = ts.astimezone(timezone.utc)
                    else:
                        ts = ts.replace(tzinfo=timezone.utc) if hasattr(ts, "replace") else ts
                    bars.append({
                        "time": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0)),
                        "tick_volume": float(row.get("Volume", 0)),
                    })
                return bars
        except Exception as yf_err:
            logger.debug(f"[MarketDataService] yfinance fetch failed for {sym}: {yf_err}")

        return []
