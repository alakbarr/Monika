# ==============================================================================
# File: analysis/tools/handlers/trade_intel/base.py
# ==============================================================================

"""
Base typing and session helpers for Trade Intel handlers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.TradeIntel")


def _get_session_and_settings(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    return session, settings


__all__ = ["logger", "_get_session_and_settings"]
