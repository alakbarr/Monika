"""
Clock Abstraction Module for Deterministic Time and Point-in-Time Simulation.
"""

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional

_simulated_now: ContextVar[datetime | None] = ContextVar("_simulated_now", default=None)
_global_simulated_now: datetime | None = None


def now() -> datetime:
    """
    Returns the current simulated datetime if set, or real datetime.now(timezone.utc).
    Always timezone-aware in UTC.
    """
    sim = _simulated_now.get() or _global_simulated_now
    if sim is not None:
        return ensure_utc(sim) or datetime.now(UTC)
    return datetime.now(UTC)


def set_simulated_now(dt: datetime | None) -> None:
    """Sets the simulated datetime globally in the current context and process fallback."""
    global _global_simulated_now
    val = ensure_utc(dt)
    _simulated_now.set(val)
    _global_simulated_now = val


def get_simulated_now() -> datetime | None:
    """Returns the currently active simulated datetime, or None if live."""
    return _simulated_now.get() or _global_simulated_now


def is_simulated() -> bool:
    """Returns True if a simulated clock is currently active."""
    return (_simulated_now.get() or _global_simulated_now) is not None


def reset_to_system_time() -> None:
    """Resets the simulated clock back to the live system clock."""
    global _global_simulated_now
    _simulated_now.set(None)
    _global_simulated_now = None


def get_eod_cutoff(as_of: datetime | None = None) -> datetime:
    """
    Calculates the point-in-time EOD cutoff for daily US market data (DXY, VIX, US Yields).
    Daily records are normalized to YYYY-MM-DD 00:00:00 UTC, but the closing values are
    only finalized at NY Close (~20:00 UTC).
    If evaluated prior to 20:00 UTC, returns the end of the previous UTC day
    (YYYY-MM-(DD-1) 23:59:59 UTC).
    If evaluated at or after 20:00 UTC, returns as_of (or clock.now()).
    """
    eff_now = ensure_utc(as_of) or now()
    if not isinstance(eff_now, datetime):
        eff_now = now()
    if eff_now.hour < 20:
        return datetime(eff_now.year, eff_now.month, eff_now.day, tzinfo=UTC) - timedelta(seconds=1)
    return eff_now


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
    if dt is None or not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@contextmanager
def frozen_time(dt: datetime | None):
    """
    Synchronous context manager to freeze simulated time deterministically per task/thread.
    """
    token = _simulated_now.set(ensure_utc(dt))
    try:
        yield
    finally:
        _simulated_now.reset(token)


@asynccontextmanager
async def async_frozen_time(dt: datetime | None):
    """
    Asynchronous context manager to freeze simulated time deterministically per coroutine.
    """
    token = _simulated_now.set(ensure_utc(dt))
    try:
        yield
    finally:
        _simulated_now.reset(token)


class _Clock:
    """Namespace object providing access to clock methods."""

    @staticmethod
    def now() -> datetime:
        return now()

    @staticmethod
    def ensure_utc(dt: datetime | None) -> datetime | None:
        return ensure_utc(dt)

    @staticmethod
    def set_simulated_now(dt: datetime | None) -> None:
        return set_simulated_now(dt)

    @staticmethod
    def get_simulated_now() -> datetime | None:
        return get_simulated_now()

    @staticmethod
    def is_simulated() -> bool:
        return is_simulated()

    @staticmethod
    def utc_now_iso() -> str:
        return utc_now_iso()

    @staticmethod
    def frozen_time(dt: datetime | None):
        return frozen_time(dt)

    @staticmethod
    def async_frozen_time(dt: datetime | None):
        return async_frozen_time(dt)

    @staticmethod
    def reset_to_system_time() -> None:
        return reset_to_system_time()

    @staticmethod
    def get_eod_cutoff(as_of: datetime | None = None) -> datetime:
        return get_eod_cutoff(as_of)


clock = _Clock()

__all__ = [
    "now",
    "set_simulated_now",
    "get_simulated_now",
    "is_simulated",
    "reset_to_system_time",
    "get_eod_cutoff",
    "utc_now_iso",
    "ensure_utc",
    "frozen_time",
    "async_frozen_time",
    "clock",
]
