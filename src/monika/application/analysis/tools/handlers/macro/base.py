# ==============================================================================
# File: analysis/tools/handlers/macro/base.py
# ==============================================================================

"""
Base execution context and database helpers for macroeconomic tool handlers.
"""

import asyncio
import logging
from typing import Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.Tools.Macro")


def _get_macro_context(args: dict, ctx: dict) -> Tuple[Optional[AsyncSession], Optional[Any], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    return session, executor, settings


async def _safe_execute(session: Optional[AsyncSession], stmt: Any, max_retries: int = 2) -> Any:
    """Execute a query on session, synchronizing with session._session_lock if present and handling transient interface contention."""
    if not session:
        return None
    lock = getattr(session, "_session_lock", None)

    _cur_task = asyncio.current_task()
    for attempt in range(max_retries):
        try:
            if lock and getattr(lock, "_owner_task", None) is not _cur_task:
                async with lock:
                    setattr(lock, "_owner_task", _cur_task)
                    try:
                        return await session.execute(stmt)
                    finally:
                        setattr(lock, "_owner_task", None)
            else:
                # No lock, or current task already holds it (executor reentrancy).
                return await session.execute(stmt)
        except Exception as e:
            err_str = str(e).lower()
            is_concurrency = (
                "another operation is in progress" in err_str
                or "cannot perform operation" in err_str
                or "concurrent operations are not permitted" in err_str
                or "provisioning a new connection" in err_str
                or "operation already in progress" in err_str
                or "recursive use of cursors not allowed" in err_str
                or "database is locked" in err_str
            )
            if is_concurrency and attempt < max_retries - 1:
                try:
                    await session.rollback()
                except Exception:
                    pass
                await asyncio.sleep(0.05)
                continue
            if "has no attribute 'execute'" in err_str or "not bound" in err_str or "nonetype" in err_str:
                logger.debug(f"_safe_execute session error (non-fatal, returning None): {e}")
                return None
            raise
