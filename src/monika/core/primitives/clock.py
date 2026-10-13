"""
Clock Abstraction Module for Deterministic Time and Point-in-Time Simulation.
"""

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, UTC
from typing import Optional

_simulated_now: ContextVar[datetime | None] = ContextVar("_simulated_now", default=None)


def now() -> datetime:
    """
    Returns the current simulated datetime if set, or real datetime.now(timezone.utc).
    Always timezone-aware in UTC.
    """
    sim = _simulated_now.get()
    if sim is not None:
        if sim.tzinfo is None:
            return sim.replace(tzinfo=UTC)
        return sim
    return datetime.now(UTC)


def set_simulated_now(dt: datetime | None) -> None:
    """Sets the simulated datetime globally in the current context."""
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    _simulated_now.set(dt)


def get_simulated_now() -> datetime | None:
    """Returns the currently active simulated datetime, or None if live."""
    return _simulated_now.get()


def is_simulated() -> bool:
    """Returns True if a simulated clock is currently active."""
    return _simulated_now.get() is not None


def utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 string format."""
    return now().isoformat()


def ensure_utc(dt: datetime | None) -> datetime | None:
    """
    Ensures datetime is timezone-aware in UTC.
    If dt is naive (e.g. retrieved from SQLite), attaches timezone.utc.
    If dt is aware, converts to UTC.
    If dt is None, returns None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@contextmanager
def frozen_time(dt: datetime | None):
    """
    Synchronous context manager to freeze simulated time deterministically per task/thread.
    """
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    token = _simulated_now.set(dt)
    try:
        yield
    finally:
        _simulated_now.reset(token)


@asynccontextmanager
async def async_frozen_time(dt: datetime | None):
    """
    Asynchronous context manager to freeze simulated time deterministically per coroutine.
    """
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    token = _simulated_now.set(dt)
    try:
        yield
    finally:
        _simulated_now.reset(token)
