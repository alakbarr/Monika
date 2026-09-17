"""
Sentiment tool handlers and self-registration.
Handles retail sentiment, funding rates, Fear & Greed Index, FXSSI sentiment, and structured sentiment metrics.
Direct execution without circular trampolines.
"""

import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.domain.sentiment_handlers import SentimentToolHandlers
from analysis.tools.registry import ToolRegistry, ToolDefinition

logger = logging.getLogger("TradingAgent.Tools.Sentiment")


def _get_sentiment_context(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], Optional[str], SentimentToolHandlers]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    handlers = getattr(executor, "sentiment_handlers", None) or SentimentToolHandlers(settings)
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    if not sym:
        sym = args.get("symbol") or getattr(executor, "symbol", None)
    if sym and isinstance(sym, str):
        sym = sym.strip().upper().replace("/", "")
    return session, sym, handlers


async def handle_get_retail_sentiment(args: dict, **ctx) -> dict:
    session, symbol, handlers = _get_sentiment_context(args, ctx)
    sym = symbol or "EURUSD"
    return await handlers.get_retail_sentiment(symbol=sym, session=session, **args)


async def handle_get_funding_rate(args: dict, **ctx) -> dict:
    session, symbol, handlers = _get_sentiment_context(args, ctx)
    sym = symbol or "BTCUSD"
    return await handlers.get_funding_rate(symbol=sym, session=session, **args)


async def handle_get_fear_greed_index(args: dict, **ctx) -> dict:
    session, _, handlers = _get_sentiment_context(args, ctx)
    return await handlers.get_fear_greed(session=session, **args)


async def handle_get_forex_sentiment(args: dict, **ctx) -> dict:
    return await handle_get_retail_sentiment(args, **ctx)


async def handle_get_fxssi_sentiment(args: dict, **ctx) -> dict:
    return await handle_get_retail_sentiment(args, **ctx)


async def handle_get_structured_sentiment(args: dict, **ctx) -> dict:
    fg = await handle_get_fear_greed_index(args, **ctx)
    ret = await handle_get_retail_sentiment(args, **ctx)
    return {
        "fear_and_greed": fg,
        "retail_sentiment": ret,
        "status": "success",
    }


def register_sentiment_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_retail_sentiment",
            description="Fetch retail trader positioning ratio (Long% vs Short%).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_retail_sentiment,
            toolset="sentiment",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_funding_rate",
            description="Fetch crypto perpetual futures funding rate.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_funding_rate,
            toolset="sentiment",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_fear_greed_index",
            description="Fetch Crypto / Market Fear & Greed Index score and sentiment category.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_fear_greed_index,
            toolset="sentiment",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_forex_sentiment",
            description="Fetch multi-broker aggregate forex retail sentiment.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_forex_sentiment,
            toolset="sentiment",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fxssi_sentiment",
            description="Fetch FXSSI retail sentiment positioning index.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_fxssi_sentiment,
            toolset="sentiment",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_structured_sentiment",
            description="Fetch structured multi-source sentiment composite.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_structured_sentiment,
            toolset="sentiment",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)


register_sentiment_tools()
