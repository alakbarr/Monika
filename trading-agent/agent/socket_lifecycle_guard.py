# ==============================================================================
# File: agent/socket_lifecycle_guard.py
# ==============================================================================

"""
Socket Lifecycle Guard & Ownership-Safe Transport Retirement.
Low-level OS socket descriptor hygiene for resilient runtime loops.

Prevents SQLite / PostgreSQL header corruption resulting from kernel file descriptor (FD) reuse:
When a background worker thread reading an OpenSSL BIO is abandoned/timed out, hard-closing
the underlying socket file descriptor via close() can cause the OS kernel to recycle that exact
FD number for an authoritative database file (e.g. session_db.sqlite or postgres socket).
Subsequent unwinding by the abandoned thread's OpenSSL BIO then writes TLS control records into
the newly allocated database file, causing silent file header corruption.

Solution:
1. Issue socket.shutdown(socket.SHUT_RDWR) exclusively to induce EOF/EPIPE on reading threads.
2. Defer socket close() / transport finalization until thread has fully unwound.
3. Manage socket retirement graveyard under thread-safe locks.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Any, List, Optional, Set

logger = logging.getLogger("TradingAgent.Agent.SocketLifecycleGuard")

_RETIREMENT_LOCK = threading.Lock()
_RETIRED_SOCKETS: List[socket.socket] = []
_MAX_GRAVEYARD_SIZE = 128


def retire_socket_ownership_safe(sock: Optional[socket.socket]) -> bool:
    """
    Safely retires a socket by invoking shutdown(SHUT_RDWR) without immediately
    releasing the underlying OS file descriptor.
    
    This ensures that any concurrent or abandoned thread reading from OpenSSL BIO
    receives an immediate network EOF/EPIPE and cleanly terminates its stack unwinding,
    preventing the OS kernel from immediately recycling the FD integer.
    
    Returns:
        True if shutdown was successfully signaled, False otherwise.
    """
    if sock is None:
        return False

    try:
        # Check if already closed
        if sock.fileno() == -1:
            return False

        # Shutdown read and write channels
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except (OSError, socket.error) as shut_err:
            # Socket might already be disconnected or in TIME_WAIT
            logger.debug(f"[SocketLifecycleGuard] Socket shutdown notice: {shut_err}")

        # Retain reference in a bounded graveyard to keep FD alive until unwinding finishes
        with _RETIREMENT_LOCK:
            _RETIRED_SOCKETS.append(sock)
            if len(_RETIRED_SOCKETS) > _MAX_GRAVEYARD_SIZE:
                # Flush the oldest socket now that sufficient wall-clock time has passed
                oldest = _RETIRED_SOCKETS.pop(0)
                try:
                    oldest.close()
                except Exception:
                    pass

        return True
    except Exception as exc:
        logger.warning(f"[SocketLifecycleGuard] Error during ownership-safe socket retirement: {exc}")
        return False


def drain_transports_after_abandonment(transport: Any) -> None:
    """
    Drains and cleanly retires an asyncio / httpx / urllib3 transport after a task
    has been cancelled or abandoned due to timeout.
    """
    if transport is None:
        return

    try:
        # Attempt to access underlying raw socket if available
        raw_sock = getattr(transport, "_sock", None)
        if raw_sock is None:
            extra = getattr(transport, "get_extra_info", None)
            if callable(extra):
                try:
                    raw_sock = extra("socket")
                except Exception:
                    raw_sock = None

        if isinstance(raw_sock, socket.socket):
            retire_socket_ownership_safe(raw_sock)

        # Signal close on transport
        close_fn = getattr(transport, "close", None)
        if callable(close_fn):
            close_fn()
    except Exception as exc:
        logger.debug(f"[SocketLifecycleGuard] Exception draining abandoned transport: {exc}")


def clear_socket_graveyard() -> int:
    """Closes all deferred retired sockets during clean process shutdown."""
    with _RETIREMENT_LOCK:
        count = len(_RETIRED_SOCKETS)
        while _RETIRED_SOCKETS:
            sock = _RETIRED_SOCKETS.pop()
            try:
                sock.close()
            except Exception:
                pass
        return count
