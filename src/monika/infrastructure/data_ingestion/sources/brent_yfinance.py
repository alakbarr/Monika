import asyncio
import logging

import yfinance as yf

logger = logging.getLogger(__name__)


async def get_brent_price() -> float | None:
    """Fetch Brent Crude (BZ=F) latest close price, prioritizing local XBRUSD OHLCV first, then yfinance (period='5d')."""
    import monika.core.primitives.clock as clock

    try:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import PriceOHLCV

        async with get_session() as session:
            row = (
                await session.execute(
                    select(PriceOHLCV.close)
                    .where(PriceOHLCV.symbol == "XBRUSD")
                    .where(PriceOHLCV.timeframe == "M15")
                    .where(PriceOHLCV.timestamp <= clock.now())
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is not None and float(row) > 0.0:
                return float(row)
    except Exception as db_err:
        logger.debug(f"Local XBRUSD lookup failed: {db_err}")

    if clock.is_simulated():
        return None

    def _fetch():
        ticker = yf.Ticker("BZ=F")
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])

    try:
        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=20.0)
    except asyncio.TimeoutError:
        logger.warning("Timed out fetching Brent price after 20.0s")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch Brent price: {e}")
        return None
