"""Sentiment domain tool handlers (News, Fear/Greed, Retail Sentiment, Funding Rates)."""

import asyncio
import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives.retry import retryable

logger = logging.getLogger("TradingAgent.SentimentHandlers")


@retryable(max_retries=2, base_delay=0.5)
async def _fetch_with_retry(fetcher: Any) -> Any:
    async with asyncio.timeout(3.5):
        return await fetcher.fetch()


_MYFXBOOK_LOCK = asyncio.Lock()
_FXSSI_LOCK = asyncio.Lock()


def _extract_sentiment_from_cached_json(
    cached_data: dict[str, Any], target_symbol: str, default_source: str = "retail_sentiment"
) -> Optional[dict[str, Any]]:
    ts_str = cached_data.get("timestamp") or cached_data.get("updated_at") or cached_data.get("fetched_at")
    if not ts_str:
        return None
    age_seconds = 0.0
    is_stale = False
    try:
        from datetime import datetime, timezone

        import monika.core.primitives.clock as clock

        dt = datetime.fromisoformat(str(ts_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_seconds = (clock.now() - dt).total_seconds()
        if age_seconds >= 14400:  # > 4h
            is_stale = True
        if age_seconds >= 86400 * 7:  # > 7 days dead
            return None
    except Exception:
        return None

    ratios_map = cached_data.get("ratios") if isinstance(cached_data.get("ratios"), dict) else cached_data
    if target_symbol:
        if isinstance(ratios_map, dict) and target_symbol in ratios_map:
            entry = ratios_map[target_symbol]
            if isinstance(entry, dict):
                res = dict(entry)
                res["cached"] = True
                if is_stale:
                    res["stale"] = True
                    res["stale_hours"] = round(age_seconds / 3600, 1)
                return res
        elif cached_data.get("symbol") == target_symbol:
            res = dict(cached_data)
            res["cached"] = True
            if is_stale:
                res["stale"] = True
                res["stale_hours"] = round(age_seconds / 3600, 1)
            return res
    else:
        if isinstance(ratios_map, dict) and ratios_map:
            res = {
                "status": "success",
                "source": cached_data.get("source", default_source),
                "ratios": ratios_map,
                "fetched_at": ts_str,
                "cached": True,
            }
            if is_stale:
                res["stale"] = True
                res["stale_hours"] = round(age_seconds / 3600, 1)
            return res
    return None


async def _read_sentiment_cache(
    session: AsyncSession, cache_keys: list[str], target_symbol: str, default_source: str
) -> Optional[dict[str, Any]]:
    import json

    from sqlalchemy import select

    from monika.infrastructure.database.models import SystemConfig

    for ck in cache_keys:
        try:
            cfg_row = (await session.execute(select(SystemConfig).where(SystemConfig.key == ck))).scalar_one_or_none()
            if cfg_row and cfg_row.value:
                cached_data = json.loads(cfg_row.value)
                res = _extract_sentiment_from_cached_json(cached_data, target_symbol, default_source=default_source)
                if res is not None:
                    return res
        except Exception:
            pass
    return None


class SentimentToolHandlers:
    """Handlers for sentiment and positioning queries."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def get_news_items(
        self, symbol: Optional[str] = None, limit: int = 10, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        if session:
            try:
                from datetime import timedelta

                from sqlalchemy import or_, select

                import monika.core.primitives.clock as clock
                from monika.infrastructure.database.models import NewsItem

                hours_back = kwargs.get("hours_back", 24)
                since = clock.now() - timedelta(hours=hours_back)
                query = (
                    select(NewsItem)
                    .where(NewsItem.fetched_at >= since)
                    .order_by(NewsItem.fetched_at.desc())
                    .limit(limit)
                )
                if symbol:
                    query = query.where(or_(NewsItem.currency_tags.contains(symbol), NewsItem.title.contains(symbol)))
                rows = (await session.execute(query)).scalars().all()
                items = [
                    {
                        "title": r.title,
                        "source": r.source,
                        "url": r.url,
                        "published_at": r.published_at.isoformat() if r.published_at else None,
                    }
                    for r in rows
                ]
                return {"news_items": items, "count": len(items)}
            except Exception as e:
                logger.warning(f"Failed to fetch news items from DB: {e}")
        return {"news_items": [], "status": "unavailable"}

    async def get_fear_greed(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        if session:
            try:
                from monika.infrastructure.data_ingestion.sources.fear_greed import FearGreedFetcher

                fetcher = FearGreedFetcher(session)
                return await _fetch_with_retry(fetcher)
            except Exception as e:
                logger.warning(f"Fear & Greed fetch failed: {e}")
        return {"status": "unavailable"}

    # Canonical alias for tool definition get_fear_greed_index
    get_fear_greed_index = get_fear_greed

    async def get_retail_sentiment(
        self, symbol: Optional[str] = None, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        target_symbol = ""
        raw_sym = symbol if symbol is not None else kwargs.get("symbol", kwargs.get("asset"))
        if raw_sym and isinstance(raw_sym, str):
            target_symbol = raw_sym.strip().upper().replace("/", "")

        if session:
            cache_keys = [f"sentiment_{target_symbol}"] if target_symbol else []
            cache_keys.extend(["myfxbook_sentiment_latest", "fxssi_sentiment_latest"])

            # 1. Try fast cache read from SystemConfig (< 4 hours)
            try:
                cached_res = await _read_sentiment_cache(session, cache_keys, target_symbol, default_source="myfxbook")
                if cached_res is not None:
                    return cached_res
            except Exception as cache_err:
                logger.debug(f"Sentiment cache check notice: {cache_err}")

            # 2. Live fetch fallback if cache missing/stale
            try:
                if target_symbol.startswith("BTC") or target_symbol.startswith("ETH"):
                    from monika.infrastructure.data_ingestion.scrapers.sentiment.binance_sentiment import (
                        BinanceSentimentFetcher,
                    )

                    fetcher = BinanceSentimentFetcher(session)
                    return await _fetch_with_retry(fetcher)
                else:
                    async with _MYFXBOOK_LOCK:
                        # Re-check cache before launching browser
                        cached_res = await _read_sentiment_cache(
                            session, cache_keys, target_symbol, default_source="myfxbook"
                        )
                        if cached_res is not None:
                            return cached_res

                        from monika.infrastructure.data_ingestion.scrapers.sentiment.myfxbook_sentiment import (
                            MyFxBookSentimentFetcher,
                        )

                        fetcher = MyFxBookSentimentFetcher(session)
                        res = await _fetch_with_retry(fetcher)
                        if isinstance(res, dict) and "error" not in res and bool(res):
                            if target_symbol and isinstance(res.get("ratios"), dict) and target_symbol in res["ratios"]:
                                return dict(res["ratios"][target_symbol])
                            return res

                    # Graceful fallback to FXSSI if MyFxBook is blocked or unavailable
                    async with _FXSSI_LOCK:
                        # Re-check cache before launching browser
                        cached_res = await _read_sentiment_cache(
                            session, ["fxssi_sentiment_latest"], target_symbol, default_source="fxssi"
                        )
                        if cached_res is not None:
                            return cached_res

                        from monika.infrastructure.data_ingestion.scrapers.sentiment.fxssi_sentiment import (
                            FXSSISentimentFetcher,
                        )

                        fxssi_fetcher = FXSSISentimentFetcher(session)
                        res = await _fetch_with_retry(fxssi_fetcher)
                        if isinstance(res, dict) and "error" not in res and bool(res):
                            if target_symbol and isinstance(res.get("ratios"), dict) and target_symbol in res["ratios"]:
                                return dict(res["ratios"][target_symbol])
                            return res
            except Exception as e:
                logger.warning(f"Retail sentiment fetch failed: {e}")
        return {"symbol": target_symbol, "status": "unavailable"} if target_symbol else {"status": "unavailable"}

    async def get_fxssi_sentiment(
        self, symbol: Optional[str] = None, session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        target_symbol = ""
        raw_sym = symbol if symbol is not None else kwargs.get("symbol", kwargs.get("asset"))
        if raw_sym and isinstance(raw_sym, str):
            target_symbol = raw_sym.strip().upper().replace("/", "")

        if session:
            cache_keys = [f"fxssi_{target_symbol}"] if target_symbol else []
            cache_keys.append("fxssi_sentiment_latest")

            # 1. Try fast cache read from SystemConfig (< 4 hours)
            try:
                cached_res = await _read_sentiment_cache(session, cache_keys, target_symbol, default_source="fxssi")
                if cached_res is not None:
                    return cached_res
            except Exception as cache_err:
                logger.debug(f"FXSSI sentiment cache check notice: {cache_err}")

            # 2. Live fetch fallback if cache missing/stale
            try:
                async with _FXSSI_LOCK:
                    # Re-check cache before launching browser
                    cached_res = await _read_sentiment_cache(session, cache_keys, target_symbol, default_source="fxssi")
                    if cached_res is not None:
                        return cached_res

                    from monika.infrastructure.data_ingestion.scrapers.sentiment.fxssi_sentiment import (
                        FXSSISentimentFetcher,
                    )

                    fxssi_fetcher = FXSSISentimentFetcher(session)
                    res = await _fetch_with_retry(fxssi_fetcher)
                    if isinstance(res, dict) and "error" not in res and bool(res):
                        if target_symbol and isinstance(res.get("ratios"), dict) and target_symbol in res["ratios"]:
                            return dict(res["ratios"][target_symbol])
                        return res
            except Exception as e:
                logger.warning(f"FXSSI sentiment fetch failed: {e}")
        return {"symbol": target_symbol, "status": "unavailable"} if target_symbol else {"status": "unavailable"}

    async def get_funding_rate(
        self, symbol: str = "BTCUSD", session: Optional[AsyncSession] = None, **kwargs
    ) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_funding_rate

        res = await handle_get_funding_rate({"symbol": symbol, **kwargs}, session=session, settings=self.settings)
        if isinstance(res, dict) and "average_funding_rate" in res and "funding_rate" not in res:
            res["funding_rate"] = res["average_funding_rate"]
        return res

    async def get_news_digest(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.news_tools import handle_get_news_digest

        return await handle_get_news_digest(kwargs, session=session, settings=self.settings)
