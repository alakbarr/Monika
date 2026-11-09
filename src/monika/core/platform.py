# ==============================================================================
# Package: monika.core
# File: platform.py
# ==============================================================================

"""
Universal Cross-Platform & Event Loop Compatibility Engine.
Provides centralized OS detection, resilient event loop configuration,
safe asynchronous subprocess execution, and normalized cross-platform path handling.
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

IS_WINDOWS: bool = sys.platform == "win32"
IS_LINUX: bool = sys.platform.startswith("linux")
IS_DARWIN: bool = sys.platform == "darwin"
IS_WINE: bool = "WINEPREFIX" in os.environ or os.path.exists("/.wine")


def patch_proactor_connection_lost() -> bool:
    """
    Safely patch asyncio._ProactorBasePipeTransport._call_connection_lost on Windows.

    Under Windows IOCP (ProactorEventLoop), when a remote client (e.g. browser WebSocket,
    HTTP client) abruptly disconnects or sends a TCP RST, WinSock marks the socket as reset.
    CPython's standard library calls `self._sock.shutdown(socket.SHUT_RDWR)` without catching
    ConnectionResetError (WinError 10054).

    When this unhandled exception is raised inside the finally block of _call_connection_lost:
    1. The exception escapes and triggers an alarming asyncio ERROR log in the event loop.
    2. Crucially, self._sock.close() and server._detach(self) are SKIPPED, leaking socket
       descriptors and leaving zombie client transports inside server._clients indefinitely.

    This patch safely wraps the shutdown call in `try...except OSError: pass`, allowing
    clean closure of the socket, proper detachment from the server, and silent teardown of
    already-severed connections without resource leaks.

    Returns:
        True if the patch was successfully applied or already present, False otherwise.
    """
    if not IS_WINDOWS:
        return False

    try:
        import asyncio.proactor_events as pe
    except ImportError:
        return False

    transport_cls = getattr(pe, "_ProactorBasePipeTransport", None)
    if transport_cls is None:
        return False

    if getattr(transport_cls, "_monika_patched_connection_lost", False):
        return True

    orig_call_connection_lost = getattr(transport_cls, "_call_connection_lost", None)
    if orig_call_connection_lost is None:
        return False

    def _safe_call_connection_lost(self: Any, exc: Any) -> None:
        if self._called_connection_lost:
            return
        try:
            self._protocol.connection_lost(exc)
        finally:
            if hasattr(self._sock, "shutdown") and self._sock.fileno() != -1:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            if self._sock is not None:
                self._sock.close()
                self._sock = None
            server = self._server
            if server is not None:
                server._detach(self)
                self._server = None
            self._called_connection_lost = True

    setattr(transport_cls, "_call_connection_lost", _safe_call_connection_lost)
    setattr(transport_cls, "_monika_patched_connection_lost", True)
    return True


if IS_WINDOWS:
    patch_proactor_connection_lost()


def configure_event_loop() -> Dict[str, Any]:
    """
    Configure and return keyword arguments for optimal event loop factory based on OS.

    - Python < 3.12: Configures default event loop policy on Windows and returns empty dict.
    - Python >= 3.12:
      - Windows: Uses ProactorEventLoop (Windows native IOCP) to prevent Winsock select()
        buffer exhaustion (WSAENOBUFS 10055) and handle high-concurrency socket pooling.
      - Linux / Darwin: Uses uvloop if installed for high-performance epoll event processing,
        or defaults to standard asyncio loop.
    """
    if sys.version_info < (3, 12):
        if IS_WINDOWS:
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass
        return {}

    if IS_WINDOWS:
        patch_proactor_connection_lost()
        proactor = getattr(asyncio, "ProactorEventLoop", None)
        if proactor is not None:
            return {"loop_factory": proactor}
        return {}
    else:
        try:
            import uvloop

            return {"loop_factory": uvloop.new_event_loop}
        except ImportError:
            return {}


def get_loop_factory() -> Dict[str, Any]:
    """Return loop_factory keyword arguments for asyncio.run() or asyncio.Runner."""
    return configure_event_loop()


def run_async(coroutine: Any, **kwargs: Any) -> Any:
    """
    Execute coroutine using asyncio.run() with optimal event loop on Windows and POSIX.
    """
    factory_kwargs = get_loop_factory()
    merged_kwargs = {**factory_kwargs, **kwargs}
    if sys.version_info < (3, 12):
        merged_kwargs.pop("loop_factory", None)
        if IS_WINDOWS:
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass
    return asyncio.run(coroutine, **merged_kwargs)


def normalize_path(path_input: Union[str, Path]) -> Path:
    """
    Normalize cross-platform file paths, resolving symlinks and unifying directory separators.
    """
    if not path_input:
        return Path(".")
    return Path(path_input).resolve()


async def safe_subprocess_run(
    cmd: List[str],
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    capture_output: bool = True,
    **kwargs: Any,
) -> Tuple[int, str, str]:
    """
    Run subprocess safely across platforms without triggering NotImplementedError.

    On Windows when SelectorEventLoop is active, asyncio.create_subprocess_exec()
    raises NotImplementedError. This function executes subprocess.run via
    asyncio.to_thread on Windows, and uses native asyncio.create_subprocess_exec on Linux.

    Returns:
        Tuple of (returncode, stdout_str, stderr_str)
    """
    if IS_WINDOWS:

        def _sync_exec():
            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                env=env or os.environ.copy(),
                timeout=timeout,
                capture_output=capture_output,
                text=True,
                encoding="utf-8",
                errors="replace",
                **kwargs,
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""

        return await asyncio.to_thread(_sync_exec)
    else:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd) if cwd else None,
                env=env or os.environ.copy(),
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
                **kwargs,
            )
            if timeout:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            else:
                stdout_bytes, stderr_bytes = await proc.communicate()

            stdout_str = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr_str = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            return proc.returncode or 0, stdout_str, stderr_str
        except NotImplementedError, AttributeError:

            def _sync_fallback():
                p = subprocess.run(
                    cmd,
                    cwd=str(cwd) if cwd else None,
                    env=env or os.environ.copy(),
                    timeout=timeout,
                    capture_output=capture_output,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **kwargs,
                )
                return p.returncode, p.stdout or "", p.stderr or ""

            return await asyncio.to_thread(_sync_fallback)


def get_platform_info() -> Dict[str, Any]:
    """
    Return normalized host platform and shell environment details for LLM prompting and tools.
    """
    os_name = "Windows" if IS_WINDOWS else ("Linux" if IS_LINUX else "macOS" if IS_DARWIN else "Unix")
    shell_name = "PowerShell 5.1" if IS_WINDOWS else "Bash (/bin/bash)"
    return {
        "os_name": os_name,
        "shell_name": shell_name,
        "is_windows": IS_WINDOWS,
        "is_linux": IS_LINUX,
        "is_darwin": IS_DARWIN,
        "is_wine": IS_WINE,
        "preferred_read_tool": "read_file",
    }


def normalize_shell_command_for_platform(command: str) -> str:
    """
    Normalizes shell command strings across host operating systems.

    On Windows, translates common Unix file-viewing idioms (e.g. `cat <path> | head -c <N>`,
    `head -n <N>`, pipelines with `grep`) into robust, native PowerShell cmdlets to prevent
    'command not found' errors when LLMs inadvertently emit POSIX commands.
    """
    if not IS_WINDOWS or not command:
        return command

    cmd = command.strip()

    # Pattern 1: cat/type/Get-Content "<path>" | head -c <num>
    m_cat_head_c = re.match(
        r'^(?:cat|type|Get-Content)\s+([^\s|]+|".+?"|\'.+?\')\s*\|\s*head\s+-c\s+(\d+)$',
        cmd,
        re.IGNORECASE,
    )
    if m_cat_head_c:
        path = m_cat_head_c.group(1)
        count = int(m_cat_head_c.group(2))
        return f"$raw = (Get-Content -Path {path} -Raw); if ($raw.Length -gt {count}) {{ $raw.Substring(0, {count}) }} else {{ $raw }}"

    # Pattern 2: cat/type/Get-Content "<path>" | head [-n <num>]
    m_cat_head_n = re.match(
        r'^(?:cat|type|Get-Content)\s+([^\s|]+|".+?"|\'.+?\')\s*\|\s*head(?:\s+(?:-n\s+)?(\d+))?$',
        cmd,
        re.IGNORECASE,
    )
    if m_cat_head_n:
        path = m_cat_head_n.group(1)
        lines = int(m_cat_head_n.group(2)) if m_cat_head_n.group(2) else 10
        return f"Get-Content -Path {path} | Select-Object -First {lines}"

    # Pattern 3: direct `head [-n <num>] "<path>"`
    m_head_direct = re.match(
        r'^head(?:\s+(?:-n\s+)?(\d+))?\s+([^\s|]+|".+?"|\'.+?\')$',
        cmd,
        re.IGNORECASE,
    )
    if m_head_direct:
        lines = int(m_head_direct.group(1)) if m_head_direct.group(1) else 10
        path = m_head_direct.group(2)
        return f"Get-Content -Path {path} | Select-Object -First {lines}"

    # Pattern 4: direct `tail [-n <num>] "<path>"`
    m_tail_direct = re.match(
        r'^tail(?:\s+(?:-n\s+)?(\d+))?\s+([^\s|]+|".+?"|\'.+?\')$',
        cmd,
        re.IGNORECASE,
    )
    if m_tail_direct:
        lines = int(m_tail_direct.group(1)) if m_tail_direct.group(1) else 10
        path = m_tail_direct.group(2)
        return f"Get-Content -Path {path} | Select-Object -Last {lines}"

    # Pattern 5: pipeline `<prefix> | head -c <num>`
    m_pipe_head_c = re.match(r"^(.+?)\s*\|\s*head\s+-c\s+(\d+)$", cmd, re.IGNORECASE)
    if m_pipe_head_c:
        prefix = m_pipe_head_c.group(1)
        count = int(m_pipe_head_c.group(2))
        return f"$txt = (({prefix}) | Out-String); if ($txt.Length -gt {count}) {{ $txt.Substring(0, {count}) }} else {{ $txt }}"

    # Pattern 6: pipeline `<prefix> | head [-n <num>]`
    m_pipe_head_n = re.match(r"^(.+?)\s*\|\s*head(?:\s+(?:-n\s+)?(\d+))?$", cmd, re.IGNORECASE)
    if m_pipe_head_n:
        prefix = m_pipe_head_n.group(1)
        lines = int(m_pipe_head_n.group(2)) if m_pipe_head_n.group(2) else 10
        return f"({prefix}) | Select-Object -First {lines}"

    # Pattern 7: pipeline `<prefix> | tail [-n <num>]`
    m_pipe_tail_n = re.match(r"^(.+?)\s*\|\s*tail(?:\s+(?:-n\s+)?(\d+))?$", cmd, re.IGNORECASE)
    if m_pipe_tail_n:
        prefix = m_pipe_tail_n.group(1)
        lines = int(m_pipe_tail_n.group(2)) if m_pipe_tail_n.group(2) else 10
        return f"({prefix}) | Select-Object -Last {lines}"

    # Pattern 8: pipeline `<prefix> | grep "pattern"`
    m_pipe_grep = re.match(r'^(.+?)\s*\|\s*grep(?:\s+-[a-zA-Z]+)?\s+([^\s|]+|".+?"|\'.+?\')$', cmd, re.IGNORECASE)
    if m_pipe_grep:
        prefix = m_pipe_grep.group(1)
        pattern = m_pipe_grep.group(2)
        return f"({prefix}) | Select-String -Pattern {pattern}"

    return cmd


__all__ = [
    "IS_WINDOWS",
    "IS_LINUX",
    "IS_DARWIN",
    "IS_WINE",
    "patch_proactor_connection_lost",
    "configure_event_loop",
    "get_loop_factory",
    "run_async",
    "normalize_path",
    "safe_subprocess_run",
    "get_platform_info",
    "normalize_shell_command_for_platform",
]
