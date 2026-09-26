# ==============================================================================
# File: agent/deadline.py
# ==============================================================================

"""
Unified Execution Deadlines & Suspectable Backend Lifecycle.
Thread-isolated watchdog timers that operate independently of event loop starvation.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Optional, Protocol, TypeVar

logger = logging.getLogger("TradingAgent.Agent.Deadline")

T = TypeVar("T")


class SuspectableBackend(Protocol):
    """Protocol for backends that can be marked suspect and retired upon timeouts."""
    def mark_suspect(self, reason: str) -> None:
        ...

    def is_suspect(self) -> bool:
        ...

    def retire_socket_safe(self) -> None:
        ...


async def run_bounded_async(
    coro: Awaitable[T],
    timeout_seconds: float,
    backend: Optional[SuspectableBackend] = None,
    timeout_message: str = "Asynchronous operation exceeded hard deadline",
) -> T:
    """
    Executes a coroutine within an asynchronous deadline.
    If a SuspectableBackend is provided and a timeout occurs, marks it suspect.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        if backend is not None:
            try:
                backend.mark_suspect(f"Timeout after {timeout_seconds:.1f}s")
                backend.retire_socket_safe()
            except Exception as e:
                logger.warning(f"[Deadline] Failed to retire suspect backend: {e}")
        logger.error(f"[Deadline] {timeout_message} ({timeout_seconds:.1f}s)")
        raise TimeoutError(f"{timeout_message} ({timeout_seconds:.1f}s)")


def run_bounded_sync(
    func: Callable[..., T],
    args: tuple = (),
    kwargs: Optional[dict] = None,
    timeout_seconds: float = 30.0,
    backend: Optional[SuspectableBackend] = None,
) -> T:
    """
    Executes a synchronous callable with an independent threading.Timer watchdog.
    """
    kwargs = kwargs or {}
    result: list = []
    error: list = []
    done_event = threading.Event()

    def _worker():
        try:
            res = func(*args, **kwargs)
            result.append(res)
        except Exception as exc:
            error.append(exc)
        finally:
            done_event.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    finished = done_event.wait(timeout=timeout_seconds)
    if not finished:
        if backend is not None:
            try:
                backend.mark_suspect(f"Sync call timed out after {timeout_seconds:.1f}s")
            except Exception:
                pass
        raise TimeoutError(f"Synchronous execution timed out after {timeout_seconds:.1f}s")

    if error:
        raise error[0]
    return result[0]
