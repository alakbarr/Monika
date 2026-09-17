"""
Unified Position Supervisor (Phase 8 - I1).
Consolidates MT5 position polling into a single high-efficiency supervisor loop,
distributing consistent position snapshots to specialized evaluators without polling contention.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Scheduler.PositionSupervisor")


class PositionSupervisor:
    """Unified supervisor for position polling, health distribution, and evaluator coordination."""

    def __init__(
        self,
        mt5_client: Any,
        settings: Optional[dict] = None,
        poll_interval_seconds: float = 10.0,
    ):
        self.mt5_client = mt5_client
        self.settings = settings or {}
        self.poll_interval = poll_interval_seconds

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._latest_positions: List[Dict[str, Any]] = []
        self._latest_account_info: Optional[Dict[str, Any]] = None
        self._last_poll_time: Optional[datetime] = None
        self._evaluators: Dict[str, Callable[[List[Dict[str, Any]], Optional[Dict[str, Any]]], Any]] = {}
        self._lock = asyncio.Lock()

    def register_evaluator(
        self,
        name: str,
        callback: Callable[[List[Dict[str, Any]], Optional[Dict[str, Any]]], Any],
    ) -> None:
        """Register a downstream evaluator to receive latest position snapshots."""
        self._evaluators[name] = callback
        logger.info(f"[PositionSupervisor] Registered evaluator: {name}")

    def unregister_evaluator(self, name: str) -> None:
        """Remove an evaluator from dispatch list."""
        self._evaluators.pop(name, None)

    async def get_latest_snapshot(self) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[datetime]]:
        """Return the latest cached positions and account info."""
        async with self._lock:
            return list(self._latest_positions), dict(self._latest_account_info) if self._latest_account_info else None, self._last_poll_time

    async def poll_once(self) -> None:
        """Fetch positions and account info once and distribute to evaluators."""
        if not self.mt5_client:
            return

        try:
            connected = await self.mt5_client.is_connected() if hasattr(self.mt5_client, "is_connected") else True
            if not connected:
                return

            positions = await self.mt5_client.get_open_positions() if hasattr(self.mt5_client, "get_open_positions") else []
            account_info = await self.mt5_client.get_account_info() if hasattr(self.mt5_client, "get_account_info") else None

            async with self._lock:
                self._latest_positions = positions or []
                self._latest_account_info = account_info
                self._last_poll_time = datetime.now(timezone.utc)

            # Distribute snapshot to registered evaluators concurrently
            for name, eval_fn in list(self._evaluators.items()):
                try:
                    import inspect
                    if inspect.iscoroutinefunction(eval_fn):
                        await eval_fn(self._latest_positions, self._latest_account_info)
                    else:
                        eval_fn(self._latest_positions, self._latest_account_info)
                except Exception as eval_err:
                    logger.warning(f"[PositionSupervisor] Evaluator '{name}' raised error: {eval_err}")

        except Exception as e:
            logger.error(f"[PositionSupervisor] Poll cycle error: {e}", exc_info=True)

    async def start(self) -> None:
        """Start background polling loop."""
        self._running = True
        logger.info(f"[PositionSupervisor] Starting supervisor loop (interval={self.poll_interval}s)")
        while self._running:
            await self.poll_once()
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Gracefully stop background loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[PositionSupervisor] Supervisor stopped.")
