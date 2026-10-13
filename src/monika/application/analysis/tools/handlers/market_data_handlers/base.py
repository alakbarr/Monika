# ==============================================================================
# File: analysis/tools/handlers/market_data/base.py
# ==============================================================================

"""
Base execution context and session resolution helpers for market data tools.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.Tools.MarketData")


def _get_session_and_symbol(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], Optional[str], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    if not sym:
        sym = args.get("symbol") or getattr(executor, "symbol", None)
    if sym and isinstance(sym, str):
        sym = sym.strip().upper().replace("/", "")
    return session, sym, settings
