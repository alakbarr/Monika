# ==============================================================================
# File: analysis/mcp/event_bridge.py
# ==============================================================================

"""
MCP EventBridge Streaming with Debounced File MTime Detection.
Institutional-grade Model Context Protocol architecture.

Monitors local state and database changes via filesystem mtime notifications
with a 200ms debounce interval, streaming real-time resource updates to
connected external MCP clients without CPU polling saturation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable, Coroutine, Dict, List, Optional, Set

logger = logging.getLogger("TradingAgent.MCP.EventBridge")

_DEFAULT_DEBOUNCE_SECONDS = 0.20


class McpEventBridge:
    """Monitors filesystem changes with debounced streaming notification hooks."""

    def __init__(
        self,
        monitored_paths: Optional[List[Path]] = None,
        debounce_seconds: float = _DEFAULT_DEBOUNCE_SECONDS,
    ):
        self.monitored_paths = monitored_paths or []
        self.debounce_seconds = debounce_seconds
        self._last_mtimes: Dict[Path, float] = {}
        self._subscribers: List[Callable[[Path, float], Coroutine[Any, Any, None]]] = []
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def add_path(self, path: Path) -> None:
        self.monitored_paths.append(path)
        if path.exists():
            self._last_mtimes[path] = path.stat().st_mtime

    def subscribe(self, callback: Callable[[Path, float], Coroutine[Any, Any, None]]) -> None:
        self._subscribers.append(callback)

    def check_for_changes(self) -> List[Path]:
        """Synchronously check for modified files."""
        changed: List[Path] = []
        for path in self.monitored_paths:
            if not path.exists():
                continue
            curr_mtime = path.stat().st_mtime
            prev_mtime = self._last_mtimes.get(path, 0.0)
            if curr_mtime > prev_mtime:
                self._last_mtimes[path] = curr_mtime
                changed.append(path)
        return changed

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.debounce_seconds)
                changed = self.check_for_changes()
                for path in changed:
                    logger.debug(f"[McpEventBridge] Detected change on {path}")
                    for sub in self._subscribers:
                        try:
                            await sub(path, self._last_mtimes[path])
                        except Exception as se:
                            logger.warning(f"[McpEventBridge] Subscriber callback error: {se}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[McpEventBridge] Error in monitor loop: {e}")

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        self._running = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
