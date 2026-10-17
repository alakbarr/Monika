"""
Safe database operation helpers that prevent PendingRollbackError cascades.

When a caller catches exceptions inside `async with get_session()` and
continues the loop, the session stays in a failed transaction state.
Subsequent queries fail with PendingRollbackError.

This module provides `safe_db_op()` which wraps individual DB operations
with proper rollback on failure.
"""

import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger("TradingAgent.SafeOps")
T = TypeVar("T")


async def _safe_expunge_all(session: AsyncSession) -> None:
    """Expunges all identity map objects, safely awaiting if mock is async."""
    expunge_fn = getattr(session, "expunge_all", None)
    if callable(expunge_fn):
        try:
            res: Any = expunge_fn()
            if inspect.isawaitable(res):
                await res
        except Exception:
            pass


async def safe_db_op(
    session: AsyncSession,
    operation: Callable,
    *args,
    default: Any = None,
    label: str = "db_op",
    **kwargs,
) -> Any:
    """Execute a DB operation with automatic rollback on failure.

    Prevents PendingRollbackError cascade by rolling back failed
    transactions before returning control to caller's loop.

    Args:
        session: Active async session
        operation: Async callable that performs DB work
        default: Value to return on failure
        label: Human-readable label for logging

    Returns:
        Operation result on success, `default` on failure.
    """
    try:
        return await operation(session, *args, **kwargs)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(session.rollback())
            await _safe_expunge_all(session)
        except Exception:
            pass
        raise
    except Exception as e:
        logger.warning(f"safe_db_op [{label}] failed: {e}")
        try:
            await asyncio.shield(session.rollback())
            await _safe_expunge_all(session)
        except Exception as rb_err:
            logger.error(f"safe_db_op [{label}] rollback failed: {rb_err}")
        return default


async def safe_commit(session: AsyncSession, label: str = "commit", max_retries: int = 3) -> bool:
    """Commit an active transaction with automatic rollback on failure.

    Prevents PendingRollbackError cascades by retrying transient SQLite lock
    contention and guaranteeing clean rollback and expunge on failure.

    Returns:
        True if commit succeeded, False if failed and rolled back.
    """
    for attempt in range(max_retries):
        try:
            await session.commit()
            return True
        except asyncio.CancelledError:
            try:
                await asyncio.shield(session.rollback())
                await _safe_expunge_all(session)
            except Exception:
                pass
            raise
        except Exception as e:
            err_str = str(e).lower()
            is_locked = "locked" in err_str or "busy" in err_str
            if is_locked and attempt < max_retries - 1:
                # If flush already invalidated the transaction, break out to clean rollback
                if not getattr(session, "is_active", True):
                    break
                logger.warning(
                    f"safe_commit [{label}] lock collision (attempt {attempt + 1}/{max_retries}): {e}. Retrying..."
                )
                await asyncio.sleep(0.05 * (2**attempt))
                continue

            logger.warning(f"safe_commit [{label}] failed: {e}. Rolling back transaction.")
            try:
                await asyncio.shield(session.rollback())
                await _safe_expunge_all(session)
            except Exception as rb_err:
                logger.error(f"safe_commit [{label}] rollback failed: {rb_err}")
            return False

    try:
        await asyncio.shield(session.rollback())
        await _safe_expunge_all(session)
    except Exception as rb_err:
        logger.error(f"safe_commit [{label}] rollback failed: {rb_err}")
    return False


async def safe_upsert(
    session: AsyncSession,
    model: type,
    values: Dict[str, Any],
    index_elements: List[str],
    update_cols: Optional[List[str]] = None,
    extra_update_values: Optional[Dict[str, Any]] = None,
) -> None:
    """Execute an upsert statement compatible with PostgreSQL and SQLite.

    Uses native ON CONFLICT DO UPDATE when supported by dialect,
    falling back to check-and-update when dialect is unknown or custom.
    """
    bind = getattr(session, "bind", None)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None) or "postgresql"

    cols_to_update = update_cols if update_cols is not None else [k for k in values.keys() if k not in index_elements]

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(model).values(values)
        set_dict: Dict[str, Any] = {col: getattr(stmt.excluded, col) for col in cols_to_update}
        if extra_update_values:
            set_dict.update(extra_update_values)
        stmt = stmt.on_conflict_do_update(index_elements=index_elements, set_=set_dict)
        await session.execute(stmt)
    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt_sqlite = sqlite_insert(model).values(values)
        set_dict = {col: getattr(stmt_sqlite.excluded, col) for col in cols_to_update}
        if extra_update_values:
            set_dict.update(extra_update_values)
        stmt_sqlite = stmt_sqlite.on_conflict_do_update(index_elements=index_elements, set_=set_dict)
        await session.execute(stmt_sqlite)
    else:
        filters = [getattr(model, col) == values[col] for col in index_elements]
        existing = (await session.execute(select(model).where(*filters))).scalars().first()
        if existing:
            for col in cols_to_update:
                if col in values:
                    setattr(existing, col, values[col])
            if extra_update_values:
                for col, val in extra_update_values.items():
                    setattr(existing, col, val)
        else:
            session.add(model(**values))
