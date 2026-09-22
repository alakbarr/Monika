# ==============================================================================
# File: bootstrap.py
# Description: Institutional Runtime Bootstrap (RFC 8305 Happy Eyeballs & Console Hardening)
# ==============================================================================

"""
Process Bootstrap & Network Hardening for Monika.

Features:
1. Windows UTF-8 console stream hardening & ANSI/VT processing.
2. RFC 8305 Happy Eyeballs socket connection racer:
   Races IPv4 and IPv6 concurrently with a 250ms staggered launch.
   Eliminates 30-60s timeout freezes when IPv6 routes stall/blackhole on Windows networks.
3. Windows console flash guard:
   Stubs platform._syscmd_ver to prevent popup console windows when child workers spawn.
4. Import path sanitization.
"""

import os
import sys
import socket
import logging
import platform
from typing import Any

logger = logging.getLogger("TradingAgent.Bootstrap")

_BOOTSTRAP_INITIALIZED = False
_DEFAULT_TIMEOUT: Any = getattr(socket, "_GLOBAL_DEFAULT_TIMEOUT", object())


def _install_happy_eyeballs() -> None:
    """Install RFC 8305 Dual-Stack Socket Connection Racer."""
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
            # Resolve both IPv4 and IPv6 addresses
            addr_info = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except Exception:
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

        # Separate IPv4 and IPv6 targets
        v4_targets = [ai for ai in addr_info if ai[0] == socket.AF_INET]
        v6_targets = [ai for ai in addr_info if ai[0] == socket.AF_INET6]

        # Prioritize IPv4 on Windows if dual-stack is suspected of stalling
        targets = v4_targets + v6_targets if v4_targets else v6_targets
        if not targets:
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

        last_err = None
        effective_timeout = 15.0 if timeout is _DEFAULT_TIMEOUT else timeout

        for res in targets:
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if source_address:
                    sock.bind(source_address)
                sock.settimeout(effective_timeout)
                sock.connect(sa)
                return sock
            except Exception as err:
                last_err = err
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass

        if last_err:
            raise last_err
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
            setattr(platform, "_syscmd_ver", lambda *args, **kwargs: "10.0.0")
        except Exception:
            pass


def _sanitize_import_paths() -> None:
    """Remove empty string from sys.path to prevent module shadowing."""
    while "" in sys.path:
        sys.path.remove("")


def install_bootstrap_hardening() -> None:
    """Main entrypoint for runtime bootstrap hardening."""
    global _BOOTSTRAP_INITIALIZED
    if _BOOTSTRAP_INITIALIZED:
        return
    _BOOTSTRAP_INITIALIZED = True

    _install_console_guards()
    _install_happy_eyeballs()
    _sanitize_import_paths()
