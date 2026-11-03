# ==============================================================================
# Package: monika.application.agent.monitors
# File: memory_supervisor.py
# Description: 24/7 Process RSS Memory Supervisor & Progressive Compactor
# ==============================================================================

from __future__ import annotations

import asyncio
import ctypes
import gc
import logging
import sys
from typing import Any, Optional

import psutil

from monika.core.primitives.event_bus import get_event_bus

logger = logging.getLogger("TradingAgent.MemorySupervisor")

# Thresholds in Megabytes
DEFAULT_WARN_MB: float = 250.0
DEFAULT_COMPACT_MB: float = 350.0
DEFAULT_HARD_LIMIT_MB: float = 500.0


class MemorySupervisor:
    """
    24/7 Process Health & RSS Memory Supervisor.
    Monitors process memory footprint, prevents OOM risks, and executes
    progressive compaction (GC gen 2, EventBus task purge, OS working set trim).
    """

    def __init__(
        self,
        interval_seconds: float = 30.0,
        warn_mb: float = DEFAULT_WARN_MB,
        compact_mb: float = DEFAULT_COMPACT_MB,
        hard_limit_mb: float = DEFAULT_HARD_LIMIT_MB,
    ):
        self.interval_seconds = interval_seconds
        self.warn_mb = warn_mb
        self.compact_mb = compact_mb
        self.hard_limit_mb = hard_limit_mb
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._process = psutil.Process()

    def get_rss_mb(self) -> float:
        """Get current process Resident Set Size (RSS) in Megabytes."""
        try:
            return float(self._process.memory_info().rss) / (1024.0 * 1024.0)
        except Exception:
            return 0.0

    def compact_memory(self, reason: str = "manual") -> dict[str, Any]:
        """
        Executes progressive memory compaction:
        1. Full Python garbage collection across all 3 generations.
        2. EventBus finished task cleanup.
        3. OS-level physical working set trim (on Windows via EmptyWorkingSet).
        """
        rss_before = self.get_rss_mb()

        # 1. Python GC
        collected = gc.collect()

        # 2. EventBus task prune
        pruned_tasks = 0
        try:
            pruned_tasks = get_event_bus().clean_finished_tasks()
        except Exception:
            pass

        # 3. OS Kernel Working Set Trim (Windows)
        os_trimmed = False
        if sys.platform.startswith("win"):
            try:
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.psapi.EmptyWorkingSet(handle)
                os_trimmed = True
            except Exception as e:
                logger.debug(f"[MemorySupervisor] EmptyWorkingSet trim error: {e}")

        rss_after = self.get_rss_mb()
        delta = rss_before - rss_after

        logger.info(
            f"[MemorySupervisor] Compaction complete ({reason}): "
            f"RSS {rss_before:.1f} MB -> {rss_after:.1f} MB (freed {delta:.1f} MB, "
            f"gc_collected={collected}, pruned_tasks={pruned_tasks}, os_trimmed={os_trimmed})"
        )
        return {
            "rss_before_mb": rss_before,
            "rss_after_mb": rss_after,
            "freed_mb": delta,
            "gc_collected": collected,
            "pruned_tasks": pruned_tasks,
            "os_trimmed": os_trimmed,
        }

    async def run_loop(self, stop_event: Optional[asyncio.Event] = None) -> None:
        """Continuous background monitoring loop."""
        self._running = True
        logger.info(
            f"[MemorySupervisor] Started 24/7 Memory Supervisor "
            f"(interval={self.interval_seconds}s, warn={self.warn_mb}MB, compact={self.compact_mb}MB)"
        )
        while self._running:
            try:
                if stop_event is not None:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
                        break
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break

                rss = self.get_rss_mb()
                if rss >= self.hard_limit_mb:
                    logger.critical(
                        f"[MemorySupervisor] CRITICAL MEMORY USAGE: {rss:.1f} MB exceeds hard limit {self.hard_limit_mb} MB!"
                    )
                    self.compact_memory(reason=f"hard_limit_exceeded_{rss:.1f}mb")
                elif rss >= self.compact_mb:
                    logger.warning(
                        f"[MemorySupervisor] Elevated memory usage: {rss:.1f} MB exceeds compact threshold {self.compact_mb} MB. Initiating compaction."
                    )
                    self.compact_memory(reason=f"compact_threshold_{rss:.1f}mb")
                elif rss >= self.warn_mb:
                    logger.warning(
                        f"[MemorySupervisor] Memory warning: {rss:.1f} MB exceeds warning threshold {self.warn_mb} MB."
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MemorySupervisor] Unexpected error in monitor loop: {e}", exc_info=True)

        logger.info("[MemorySupervisor] Monitor loop stopped.")

    def start(self) -> asyncio.Task:
        """Start the background monitor task."""
        if self._task is not None and not self._task.done():
            return self._task
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self.run_loop(), name="memory_supervisor_loop")
        return self._task

    def stop(self) -> None:
        """Stop the background monitor task."""
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()


async def run_memory_supervisor(
    stop_event: Optional[asyncio.Event] = None,
    interval_seconds: float = 30.0,
    warn_mb: float = DEFAULT_WARN_MB,
    compact_mb: float = DEFAULT_COMPACT_MB,
    hard_limit_mb: float = DEFAULT_HARD_LIMIT_MB,
) -> None:
    """Coroutine entrypoint for running the memory supervisor."""
    supervisor = MemorySupervisor(
        interval_seconds=interval_seconds,
        warn_mb=warn_mb,
        compact_mb=compact_mb,
        hard_limit_mb=hard_limit_mb,
    )
    await supervisor.run_loop(stop_event=stop_event)


__all__ = [
    "MemorySupervisor",
    "run_memory_supervisor",
    "DEFAULT_WARN_MB",
    "DEFAULT_COMPACT_MB",
    "DEFAULT_HARD_LIMIT_MB",
]
