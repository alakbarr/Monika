import asyncio
import logging

import yfinance as yf

logger = logging.getLogger(__name__)


async def get_brent_price() -> float | None:
    """Fetch Brent Crude (BZ=F) latest close price from yfinance in non-blocking worker thread."""

    def _fetch():
        ticker = yf.Ticker("BZ=F")
        hist = ticker.history(period="1d")
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
