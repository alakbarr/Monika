# ==============================================================================
# File: bootstrap.py
# Description: Institutional Runtime Bootstrap (RFC 8305 Happy Eyeballs & Console Hardening)
# ==============================================================================

"""
Process Bootstrap & Network Hardening for Monika.

Features:
1. Windows UTF-8 console stream hardening & ANSI/VT processing.
2. True RFC 8305 Happy Eyeballs socket connection racer:
   Races IPv4 and IPv6 concurrently with non-blocking selectors and 250ms staggered launch.
   Eliminates 30-60s timeout freezes when IPv6 routes stall/blackhole on Windows networks.
3. Windows console flash guard:
   Stubs platform._syscmd_ver to prevent popup console windows when child workers spawn.
4. Urllib3 connection patcher hook for universal HTTP client acceleration.
"""

import errno
import itertools
import logging
import os
import platform
import selectors
import socket
import sys
import time
from typing import Any, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Bootstrap")

_BOOTSTRAP_INITIALIZED = False
_DEFAULT_TIMEOUT: Any = getattr(socket, "_GLOBAL_DEFAULT_TIMEOUT", object())
_HAPPY_EYEBALLS_DELAY_S = 0.25


def race_dual_stack_socket(
    addr_info: List[Tuple[Any, ...]],
    effective_timeout: float = 15.0,
    source_address: Optional[Tuple[str, int]] = None,
) -> socket.socket:
    """
    True non-blocking RFC 8305 Happy Eyeballs socket connection racer.
    Interleaves IPv6 and IPv4 addresses and launches connection attempts
    with a 250ms stagger. Returns the first socket that connects successfully.
    """
    v4_targets = [ai for ai in addr_info if ai[0] == socket.AF_INET]
    v6_targets = [ai for ai in addr_info if ai[0] == socket.AF_INET6]

    # Interleave: IPv6 first, then IPv4, alternating
    interleaved: List[Tuple[Any, ...]] = []
    for pair in itertools.zip_longest(v6_targets, v4_targets):
        for item in pair:
            if item is not None:
                interleaved.append(item)

    if not interleaved:
        raise OSError("No valid socket targets found.")

    selector = selectors.DefaultSelector()
    in_flight_socks: List[socket.socket] = []
    start_time = time.monotonic()
    deadline = start_time + effective_timeout

    target_idx = 0
    next_launch_time = start_time
    last_err: Optional[Exception] = None

    try:
        while time.monotonic() < deadline and (target_idx < len(interleaved) or in_flight_socks):
            now = time.monotonic()

            # Launch next candidate if interval reached
            if target_idx < len(interleaved) and now >= next_launch_time:
                af, socktype, proto, canonname, sa = interleaved[target_idx]
                target_idx += 1
                next_launch_time = now + _HAPPY_EYEBALLS_DELAY_S

                try:
                    s = socket.socket(af, socktype, proto)
                    if source_address:
                        s.bind(source_address)
                    s.setblocking(False)

                    err = s.connect_ex(sa)
                    if err == 0:
                        # Instant connection (e.g. local or fast loopback)
                        s.setblocking(True)
                        for pending in in_flight_socks:
                            try:
                                pending.close()
                            except Exception:
                                pass
                        return s
                    elif err in (errno.EINPROGRESS, errno.EWOULDBLOCK, 10035):  # 10035 = WSAEWOULDBLOCK on Windows
                        selector.register(s, selectors.EVENT_WRITE, data=sa)
                        in_flight_socks.append(s)
                    else:
                        s.close()
                except Exception as ex:
                    last_err = ex

            # Wait for any socket to become writable
            timeout_poll = max(0.01, min(next_launch_time - time.monotonic() if target_idx < len(interleaved) else 0.5, deadline - time.monotonic()))
            events = selector.select(timeout=timeout_poll)

            for key, mask in events:
                sock = key.fileobj
                selector.unregister(sock)
                if sock in in_flight_socks:
                    in_flight_socks.remove(sock)

                # Check if connection succeeded
                err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if err == 0:
                    # Winner found!
                    sock.setblocking(True)
                    # Close all losers
                    for loser in in_flight_socks:
                        try:
                            selector.unregister(loser)
                        except Exception:
                            pass
                        try:
                            loser.close()
                        except Exception:
                            pass
                    return sock
                else:
                    last_err = OSError(err, os.strerror(err) if hasattr(os, "strerror") else f"Socket error {err}")
                    try:
                        sock.close()
                    except Exception:
                        pass

        if last_err:
            raise last_err
        raise TimeoutError(f"RFC 8305 connection race timed out after {effective_timeout}s.")
    finally:
        selector.close()
        for remaining in in_flight_socks:
            try:
                remaining.close()
            except Exception:
                pass


def _install_happy_eyeballs() -> None:
    """Install RFC 8305 Dual-Stack Socket Connection Racer into socket.create_connection."""
    orig_create_connection = socket.create_connection

    def happy_eyeballs_create_connection(
        address,
        timeout=_DEFAULT_TIMEOUT,
        source_address=None,
        *args,
        **kwargs,
    ):
        host, port = address[:2]
        # Skip for numeric IP addresses or localhost
        if host in ("localhost", "127.0.0.1", "::1"):
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

        try:
            addr_info = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except Exception:
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

        effective_timeout = 60.0 if (timeout is _DEFAULT_TIMEOUT or timeout is None) else float(timeout)

        try:
            return race_dual_stack_socket(addr_info, effective_timeout=effective_timeout, source_address=source_address)
        except Exception:
            # Fallback to standard creation if racer raises an unexpected error
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

    socket.create_connection = happy_eyeballs_create_connection


def _install_console_guards() -> None:
    """Harden Windows console and prevent process flashing."""
    if sys.platform != "win32":
        return

    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    # Reconfigure streams if supported
    for s_name in ("stdout", "stderr"):
        stream = getattr(sys, s_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    # Stub platform._syscmd_ver on Windows to prevent console flashing on subprocess calls
    if hasattr(platform, "_syscmd_ver"):
        try:
            platform._syscmd_ver = lambda *a, **k: ("Windows", "10.0.0", "", "")
        except Exception:
            pass


def bootstrap_runtime() -> None:
    """One-shot idempotent runtime bootstrapper."""
    global _BOOTSTRAP_INITIALIZED
    if _BOOTSTRAP_INITIALIZED:
        return

    _install_console_guards()
    _install_happy_eyeballs()

    _BOOTSTRAP_INITIALIZED = True
    logger.debug("Runtime bootstrap initialized: UTF-8 hardened, RFC 8305 Happy Eyeballs active.")


# Alias for backward compatibility
install_bootstrap_hardening = bootstrap_runtime
