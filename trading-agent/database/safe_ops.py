"""
Safe database operation helpers that prevent PendingRollbackError cascades.

When a caller catches exceptions inside `async with get_session()` and
continues the loop, the session stays in a failed transaction state.
Subsequent queries fail with PendingRollbackError.

This module provides `safe_db_op()` which wraps individual DB operations
with proper rollback on failure.
"""
import asyncio
import logging
from typing import TypeVar, Callable, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger('TradingAgent.SafeOps')
T = TypeVar('T')


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
            await session.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        logger.warning(f"safe_db_op [{label}] failed: {e}")
        try:
            await session.rollback()
        except Exception as rb_err:
            logger.error(f"safe_db_op [{label}] rollback failed: {rb_err}")
        return default


async def safe_commit(session: AsyncSession, label: str = "commit") -> bool:
    """Commit an active transaction with automatic rollback on failure.
    
    Returns:
        True if commit succeeded, False if failed and rolled back.
    """
    try:
        await session.commit()
        return True
    except asyncio.CancelledError:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        logger.warning(f"safe_commit [{label}] failed: {e}. Rolling back transaction.")
        try:
            await session.rollback()
        except Exception as rb_err:
            logger.error(f"safe_commit [{label}] rollback failed: {rb_err}")
        return False
