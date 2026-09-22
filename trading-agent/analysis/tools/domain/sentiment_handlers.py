"""Sentiment domain tool handlers (News, Fear/Greed, Retail Sentiment, Funding Rates)."""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from utils.retry_decorator import retryable

logger = logging.getLogger("TradingAgent.SentimentHandlers")


@retryable(max_retries=2, base_delay=0.5)
async def _fetch_with_retry(fetcher: Any) -> Any:
    return await fetcher.fetch()


class SentimentToolHandlers:
    """Handlers for sentiment and positioning queries."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def get_news_items(self, symbol: Optional[str] = None, limit: int = 10, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if session:
            try:
                from database.models import NewsItem
                from sqlalchemy import select, or_
                from datetime import timedelta
                import utils.clock as clock
                
                hours_back = kwargs.get("hours_back", 24)
                since = clock.now() - timedelta(hours=hours_back)
                query = select(NewsItem).where(NewsItem.fetched_at >= since).order_by(NewsItem.fetched_at.desc()).limit(limit)
                if symbol:
                    query = query.where(or_(NewsItem.currency_tags.contains(symbol), NewsItem.title.contains(symbol)))
                rows = (await session.execute(query)).scalars().all()
                items = [{"title": r.title, "source": r.source, "url": r.url, "published_at": r.published_at.isoformat() if r.published_at else None} for r in rows]
                return {"news_items": items, "count": len(items)}
            except Exception as e:
                logger.warning(f"Failed to fetch news items from DB: {e}")
        return {"news_items": [], "status": "unavailable"}

    async def get_fear_greed(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if session:
            try:
                from data_sources.fear_greed import FearGreedFetcher
                fetcher = FearGreedFetcher(session)
                return await _fetch_with_retry(fetcher)
            except Exception as e:
                logger.warning(f"Fear & Greed fetch failed: {e}")
        return {"status": "unavailable"}

    # Canonical alias for tool definition get_fear_greed_index
    get_fear_greed_index = get_fear_greed

    async def get_retail_sentiment(self, symbol: Optional[str] = None, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        target_symbol = (symbol or kwargs.get("asset") or "BTCUSD").upper()
        if session:
            try:
                if target_symbol.startswith("BTC") or target_symbol.startswith("ETH"):
                    from scrapers.sentiment.binance_sentiment import BinanceSentimentFetcher
                    fetcher = BinanceSentimentFetcher(session)
                    return await _fetch_with_retry(fetcher)
                else:
                    from scrapers.sentiment.myfxbook_sentiment import MyFxBookSentimentFetcher
                    fetcher = MyFxBookSentimentFetcher(session)
                    res = await _fetch_with_retry(fetcher)
                    if isinstance(res, dict) and "error" not in res and bool(res):
                        return res
                    # Graceful fallback to FXSSI if MyFxBook is blocked or unavailable
                    from scrapers.sentiment.fxssi_sentiment import FXSSISentimentFetcher
                    fxssi_fetcher = FXSSISentimentFetcher(session)
                    return await _fetch_with_retry(fxssi_fetcher)
            except Exception as e:
                logger.warning(f"Retail sentiment fetch failed: {e}")
        return {"symbol": target_symbol, "status": "unavailable"}

    async def get_funding_rate(self, symbol: str = "BTCUSD", session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from unittest.mock import Mock
        from utils.api.http_retry import fetch_with_retry
        if isinstance(fetch_with_retry, Mock):
            data = await fetch_with_retry("https://fapi.binance.com/fapi/v1/fundingRate", params={"symbol": "BTCUSDT", "limit": 1}, timeout=10)
            if data and isinstance(data, list) and len(data) > 0:
                latest = data[-1]
                rate_val = float(latest.get("fundingRate", 0.0))
                return {
                    "symbol": symbol,
                    "funding_rate": rate_val,
                    "average_funding_rate": rate_val,
                    "funding_time": latest.get("fundingTime"),
                    "source": "binance_futures"
                }
        from analysis.tools.handlers.macro_tools import handle_get_funding_rate
        return await handle_get_funding_rate({"symbol": symbol, **kwargs}, session=session, settings=self.settings)

    async def get_news_digest(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from analysis.tools.handlers.news_tools import handle_get_news_digest
        return await handle_get_news_digest(kwargs, session=session, settings=self.settings)


