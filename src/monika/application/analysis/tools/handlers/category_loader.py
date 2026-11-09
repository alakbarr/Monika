# ==============================================================================
# File: analysis/tools/handlers/category_loader.py
# ==============================================================================

"""
Progressive tool category loader and composite context tools.
Direct execution without circular trampolines.
"""

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.tools.base_handler import ToolHandler
from monika.application.analysis.tools.registry import register_tool


async def handle_load_tool_category(args: dict, **kwargs) -> Any:
    from monika.application.analysis.tools.tool_registry import ProgressiveToolRegistry

    reg = ProgressiveToolRegistry()
    return reg.load_category(args.get("category", ""))


async def handle_get_market_context(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    symbol = sym or args.get("symbol") or getattr(executor, "symbol", "")
    from monika.application.analysis.tools.composite_tools import execute_market_context

    return await execute_market_context(executor, symbol)


async def handle_get_institutional_data(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    symbol = sym or args.get("symbol") or getattr(executor, "symbol", "")
    cot_code = args.get("cot_code")
    from monika.application.analysis.tools.composite_tools import execute_institutional_data

    return await execute_institutional_data(executor, symbol, cot_code=cot_code)


async def handle_get_macro_rates(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    from monika.application.analysis.tools.composite_tools import execute_macro_rates

    return await execute_macro_rates(executor, currencies=args.get("currencies"))


async def handle_get_macro_sentiment(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    from monika.application.analysis.tools.composite_tools import execute_macro_sentiment

    return await execute_macro_sentiment(executor, symbols=args.get("symbols"))


async def handle_get_macro_events(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    from monika.application.analysis.tools.composite_tools import execute_macro_events

    return await execute_macro_events(
        executor, days_ahead=args.get("days_ahead", 3), hours_back=args.get("hours_back", 24)
    )


async def handle_get_crypto_context(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    from monika.application.analysis.tools.composite_tools import execute_crypto_context

    return await execute_crypto_context(executor, symbols=args.get("symbols"))


async def handle_get_portfolio_state(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    from monika.application.analysis.tools.composite_tools import execute_portfolio_state

    return await execute_portfolio_state(executor, symbol=args.get("symbol"))


@register_tool("load_tool_category", aliases=["load_category"], category="GENERAL", parallel_safe=False)
class LoadToolCategoryHandler(ToolHandler):
    name = "load_tool_category"
    category = "GENERAL"
    parallel_safe = False

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_load_tool_category(args, **kwargs)


@register_tool("get_market_context", aliases=["market_context"], category="GENERAL", parallel_safe=True)
class GetMarketContextHandler(ToolHandler):
    name = "get_market_context"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_market_context(args, session=session, executor=executor, **kwargs)


@register_tool("get_institutional_data", aliases=["institutional_data"], category="GENERAL", parallel_safe=True)
class GetInstitutionalDataHandler(ToolHandler):
    name = "get_institutional_data"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_institutional_data(args, session=session, executor=executor, **kwargs)


@register_tool("get_macro_rates", aliases=["macro_rates"], category="GENERAL", parallel_safe=True)
class GetMacroRatesHandler(ToolHandler):
    name = "get_macro_rates"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_macro_rates(args, session=session, executor=executor, **kwargs)


@register_tool("get_macro_sentiment", aliases=["macro_sentiment"], category="GENERAL", parallel_safe=True)
class GetMacroSentimentHandler(ToolHandler):
    name = "get_macro_sentiment"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_macro_sentiment(args, session=session, executor=executor, **kwargs)


@register_tool("get_macro_events", aliases=["macro_events"], category="GENERAL", parallel_safe=True)
class GetMacroEventsHandler(ToolHandler):
    name = "get_macro_events"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_macro_events(args, session=session, executor=executor, **kwargs)


@register_tool("get_crypto_context", aliases=["crypto_context"], category="GENERAL", parallel_safe=True)
class GetCryptoContextHandler(ToolHandler):
    name = "get_crypto_context"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_crypto_context(args, session=session, executor=executor, **kwargs)


@register_tool("get_portfolio_state", aliases=["portfolio_state"], category="GENERAL", parallel_safe=True)
class GetPortfolioStateHandler(ToolHandler):
    name = "get_portfolio_state"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_portfolio_state(args, session=session, executor=executor, **kwargs)


async def handle_search_tools(args: dict, **kwargs) -> Any:
    from monika.application.analysis.tools.tool_registry import ProgressiveToolRegistry

    reg = ProgressiveToolRegistry()
    query = args.get("query", "")
    limit = args.get("limit", 5)
    return reg.search_tools(query=query, limit=limit)


async def handle_describe_tool(args: dict, **kwargs) -> Any:
    from monika.application.analysis.tools.tool_registry import ProgressiveToolRegistry

    reg = ProgressiveToolRegistry()
    tool_name = args.get("tool_name", "")
    schema = reg.describe_tool(tool_name)
    if not schema:
        return {"error": f"Tool '{tool_name}' not found in registry."}
    return schema


@register_tool("search_tools", aliases=["tool_search"], category="GENERAL", parallel_safe=True)
class SearchToolsHandler(ToolHandler):
    name = "search_tools"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_search_tools(args, **kwargs)


@register_tool("describe_tool", aliases=["tool_describe"], category="GENERAL", parallel_safe=True)
class DescribeToolHandler(ToolHandler):
    name = "describe_tool"
    category = "GENERAL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_describe_tool(args, **kwargs)
