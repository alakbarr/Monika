"""
Safe database operation helpers that prevent PendingRollbackError cascades.

When a caller catches exceptions inside `async with get_session()` and
continues the loop, the session stays in a failed transaction state.
Subsequent queries fail with PendingRollbackError.

This module provides `safe_db_op()` and `safe_nested_db_op()` which wrap individual
DB operations with proper savepoint/rollback isolation on failure.
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
    nested: bool = False,
    **kwargs,
) -> Any:
    """Execute a DB operation with automatic rollback/savepoint isolation on failure.

    Prevents PendingRollbackError cascades. When `nested=True` is specified, wraps
    the operation in a SAVEPOINT (`session.begin_nested()`), ensuring that an inner
    failure rolls back ONLY to the savepoint without discarding uncommitted work
    in the outer parent transaction.

    Args:
        session: Active async session
        operation: Async callable that performs DB work
        default: Value to return on failure
        label: Human-readable label for logging
        nested: If True, uses session.begin_nested() (SAVEPOINT) to isolate from parent tx

    Returns:
        Operation result on success, `default` on failure.
    """
    if not getattr(session, "is_active", True):
        logger.warning(f"safe_db_op [{label}] skipped: session is inactive/closed.")
        return default

    if nested:
        try:
            async with session.begin_nested():
                return await operation(session, *args, **kwargs)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(session.rollback())
                await _safe_expunge_all(session)
            except Exception:
                pass
            raise
        except Exception as e:
            logger.warning(f"safe_db_op [{label}] nested sub-op failed (rolled back to savepoint): {e}")
            return default

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


async def safe_nested_db_op(
    session: AsyncSession,
    operation: Callable,
    *args,
    default: Any = None,
    label: str = "nested_db_op",
    **kwargs,
) -> Any:
    """Convenience helper: Execute a DB operation isolated inside a SAVEPOINT.

    Guarantees that sub-operation failure never destroys parent transaction state.
    """
    return await safe_db_op(session, operation, *args, default=default, label=label, nested=True, **kwargs)


async def safe_commit(session: AsyncSession, label: str = "commit", max_retries: int = 1) -> bool:
    """Commit an active transaction with guaranteed automatic rollback on failure.

    Guarantees clean rollback and expunge on failure, preventing PendingRollbackError cascades.
    Note: In SQLAlchemy 2.0, once commit fails, the transaction is invalidated and must be rolled back.

    Returns:
        True if commit succeeded, False if failed and rolled back.
    """
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
        logger.warning(f"safe_commit [{label}] failed: {e}. Rolling back transaction cleanly.")
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
    bind = getattr(session, "bind", None) or (session.get_bind() if hasattr(session, "get_bind") else None)
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
