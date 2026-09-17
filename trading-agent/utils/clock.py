"""
Clock Abstraction Module for Deterministic Time and Point-in-Time Simulation.
"""
from datetime import datetime, timezone
from contextvars import ContextVar
from contextlib import contextmanager, asynccontextmanager
from typing import Optional

_simulated_now: ContextVar[Optional[datetime]] = ContextVar('_simulated_now', default=None)


def now() -> datetime:
    """
    Returns the current simulated datetime if set, or real datetime.now(timezone.utc).
    Always timezone-aware in UTC.
    """
    sim = _simulated_now.get()
    if sim is not None:
        if sim.tzinfo is None:
            return sim.replace(tzinfo=timezone.utc)
        return sim
    return datetime.now(timezone.utc)


def set_simulated_now(dt: Optional[datetime]) -> None:
    """Sets the simulated datetime globally in the current context."""
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    _simulated_now.set(dt)


def get_simulated_now() -> Optional[datetime]:
    """Returns the currently active simulated datetime, or None if live."""
    return _simulated_now.get()


def is_simulated() -> bool:
    """Returns True if a simulated clock is currently active."""
    return _simulated_now.get() is not None


def utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 string format."""
    return now().isoformat()


@contextmanager
def frozen_time(dt: Optional[datetime]):
    """
    Synchronous context manager to freeze simulated time deterministically per task/thread.
    """
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    token = _simulated_now.set(dt)
    try:
        yield
    finally:
        _simulated_now.reset(token)


@asynccontextmanager
async def async_frozen_time(dt: Optional[datetime]):
    """
    Asynchronous context manager to freeze simulated time deterministically per coroutine.
    """
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    token = _simulated_now.set(dt)
    try:
        yield
    finally:
        _simulated_now.reset(token)
