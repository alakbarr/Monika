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
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

IS_WINDOWS: bool = sys.platform == "win32"
IS_LINUX: bool = sys.platform.startswith("linux")
IS_DARWIN: bool = sys.platform == "darwin"
IS_WINE: bool = "WINEPREFIX" in os.environ or os.path.exists("/.wine")


def configure_event_loop() -> Dict[str, Any]:
    """
    Configure and return keyword arguments for optimal event loop factory based on OS.

    - Python < 3.12: Configures event loop policy on Windows and returns empty dict.
    - Python >= 3.12:
      - Windows: Uses SelectorEventLoop for compatibility with psycopg / psycopg3.
      - Linux / Darwin: Uses uvloop if installed for high-performance epoll event processing,
        or defaults to standard asyncio loop.
    """
    if sys.version_info < (3, 12):
        if IS_WINDOWS:
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass
        return {}

    if IS_WINDOWS:
        return {"loop_factory": asyncio.SelectorEventLoop}
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
    Execute coroutine using asyncio.run() with SelectorEventLoop on Windows.
    """
    factory_kwargs = get_loop_factory()
    merged_kwargs = {**factory_kwargs, **kwargs}
    if sys.version_info < (3, 12):
        merged_kwargs.pop("loop_factory", None)
        if IS_WINDOWS:
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
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


__all__ = [
    "IS_WINDOWS",
    "IS_LINUX",
    "IS_DARWIN",
    "IS_WINE",
    "configure_event_loop",
    "get_loop_factory",
    "run_async",
    "normalize_path",
    "safe_subprocess_run",
]
