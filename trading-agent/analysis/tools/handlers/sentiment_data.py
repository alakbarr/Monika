# ==============================================================================
# File: analysis/tools/handlers/sentiment_data.py
# ==============================================================================

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool


@register_tool("get_market_correlations", aliases=["correlations", "asset_correlations"], category="SENTIMENT", parallel_safe=True)
class GetMarketCorrelationsHandler(ToolHandler):
    name = "get_market_correlations"
    category = "SENTIMENT"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        if executor and hasattr(executor, "_tool_get_market_correlations"):
            return await executor._tool_get_market_correlations(args)
        return {"error": "Market correlations tool requires executor context"}


@register_tool("web_search", aliases=["search_web", "google_search"], category="SENTIMENT", parallel_safe=True)
class WebSearchHandler(ToolHandler):
    name = "web_search"
    category = "SENTIMENT"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        if executor and hasattr(executor, "_tool_web_search"):
            return await executor._tool_web_search(args)
        from analysis.tools.handlers.news_tools import handle_web_search
        return await handle_web_search(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_retail_sentiment", aliases=["retail_sentiment"], category="SENTIMENT", parallel_safe=True)
class GetRetailSentimentHandler(ToolHandler):
    name = "get_retail_sentiment"
    category = "SENTIMENT"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        if executor and hasattr(executor, "_tool_get_retail_sentiment"):
            return await executor._tool_get_retail_sentiment(args)
        from analysis.tools.domain.sentiment_handlers import SentimentToolHandlers
        return await SentimentToolHandlers(self.settings).get_retail_sentiment(symbol=args.get("symbol", ""), session=session)


@register_tool("get_forex_sentiment", aliases=["forex_sentiment"], category="SENTIMENT", parallel_safe=True)
class GetForexSentimentHandler(ToolHandler):
    name = "get_forex_sentiment"
    category = "SENTIMENT"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        if executor and hasattr(executor, "_tool_get_forex_sentiment"):
            return await executor._tool_get_forex_sentiment(args)
        from analysis.tools.handlers.sentiment_tools import handle_get_forex_sentiment
        return await handle_get_forex_sentiment(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_fxssi_sentiment", aliases=["fxssi_sentiment"], category="SENTIMENT", parallel_safe=True)
class GetFxssiSentimentHandler(ToolHandler):
    name = "get_fxssi_sentiment"
    category = "SENTIMENT"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        if executor and hasattr(executor, "_tool_get_fxssi_sentiment"):
            return await executor._tool_get_fxssi_sentiment(args)
        from analysis.tools.handlers.sentiment_tools import handle_get_fxssi_sentiment
        return await handle_get_fxssi_sentiment(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_news_digest", aliases=["get_news", "news_digest"], category="SENTIMENT", parallel_safe=True)
class GetNewsDigestHandler(ToolHandler):
    name = "get_news_digest"
    category = "SENTIMENT"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        if executor and hasattr(executor, "_tool_get_news_digest"):
            return await executor._tool_get_news_digest(args)
        from analysis.tools.handlers.news_tools import handle_get_news_digest
        return await handle_get_news_digest(args, session=session, executor=executor, **kwargs)


@register_tool("get_news_items", aliases=["get_news_item", "news_items"], category="SENTIMENT", parallel_safe=True)
class GetNewsItemsHandler(ToolHandler):
    name = "get_news_items"
    category = "SENTIMENT"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        if executor and hasattr(executor, "_tool_get_news_items"):
            return await executor._tool_get_news_items(args)
        from analysis.tools.domain.sentiment_handlers import SentimentToolHandlers
        return await SentimentToolHandlers(self.settings).get_news_items(symbol=args.get("symbol"), limit=args.get("limit", 5), session=session)
