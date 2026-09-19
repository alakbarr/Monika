"""
Pure async background review and reflection engine for post-trade learning.
Runs on the main asyncio event loop without raw OS threads to preserve asyncpg pool stability.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("TradingAgent.BackgroundReview")


class BackgroundReviewEngine:
    """
    Decoupled async worker that processes closed trade outcomes in the background.
    Reflects on trade performance, filters transient/infrastructure errors from permanent memory,
    and invokes skill crystallization when setups meet statistical confidence thresholds.
    """

    # Transient infrastructure errors that should NOT be captured as trading strategy lessons
    DO_NOT_CAPTURE: Set[str] = frozenset({
        "broker_connection_lost",
        "spread_widened_temporarily",
        "api_rate_limited",
        "mt5_timeout_reconnected",
        "transient_network_error",
        "session_closed_normal",
        "server_maintenance",
        "ping_timeout",
    })

    def __init__(
        self,
        settings: Optional[dict] = None,
        reflector: Optional[Any] = None,
        crystallizer: Optional[Any] = None,
        max_queue_size: int = 100,
    ):
        self.settings = settings or {}
        self.reflector = reflector
        if self.reflector is None:
            try:
                from analysis.providers.llm_factory import get_client_for_task
                from analysis.memory.reflector import TradeReflector
                aux_client = get_client_for_task("trade_reflection", self.settings)
                if aux_client:
                    self.reflector = TradeReflector(llm_client=aux_client)
                    logger.info(f"BackgroundReviewEngine initialized with auxiliary model: {getattr(aux_client, 'model', 'default')}")
            except Exception as e:
                logger.debug(f"Could not auto-initialize TradeReflector: {e}")
        self.crystallizer = crystallizer
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self.processed_count: int = 0
        self.discarded_count: int = 0

    def start(self) -> asyncio.Task:
        """Starts the background reflection worker on the active asyncio event loop."""
        if self._worker_task is None or self._worker_task.done():
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop(), name="bg-trade-reflection-worker")
            logger.info("BackgroundReviewEngine worker task started.")
        return self._worker_task

    async def stop(self) -> None:
        """Stops the worker task cleanly."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("BackgroundReviewEngine worker task stopped.")

    async def schedule_review(self, trade_outcome: Dict[str, Any]) -> bool:
        """
        Enqueues a closed trade outcome for background reflection without blocking trade execution.
        Returns True if enqueued, False if dropped due to full queue.
        """
        if not trade_outcome or not isinstance(trade_outcome, dict):
            return False

        try:
            self._queue.put_nowait(trade_outcome)
            logger.debug(f"Enqueued trade outcome for background review: ticket={trade_outcome.get('ticket')}")
            return True
        except asyncio.QueueFull:
            logger.warning("BackgroundReviewEngine queue full; dropping review request to prevent lag.")
            return False

    async def _worker_loop(self) -> None:
        """Continuously pulls closed trade items and runs reflection pipeline."""
        while self._running:
            try:
                outcome = await self._queue.get()
                await self._process_single_outcome(outcome)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Unexpected error in background review loop: {exc}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _process_single_outcome(self, outcome: Dict[str, Any]) -> None:
        """Processes a single trade outcome."""
        # 1. Negative constraint filtering
        error_reason = str(outcome.get("close_reason", "") or outcome.get("error_code", "")).lower()
        if any(bad in error_reason for bad in self.DO_NOT_CAPTURE):
            logger.info(
                f"[BackgroundReview] Skipping lesson capture for transient event '{error_reason}' on "
                f"ticket {outcome.get('ticket')} (filtered by DO_NOT_CAPTURE)."
            )
            self.discarded_count += 1
            return

        # 2. Invoke reflector if available
        reflection = None
        if self.reflector:
            try:
                if hasattr(self.reflector, "reflect_on_trade"):
                    reflection = await self.reflector.reflect_on_trade(outcome)
            except Exception as ref_err:
                logger.warning(f"[BackgroundReview] Reflector failed on ticket {outcome.get('ticket')}: {ref_err}")

        # 3. If crystallization is qualified, evaluate
        symbol = outcome.get("symbol")
        pnl = outcome.get("profit_loss", 0.0) or outcome.get("outcome_pnl_usd", 0.0)
        if self.crystallizer and symbol and pnl > 0:
            try:
                if hasattr(self.crystallizer, "evaluate_and_crystallize"):
                    # If DB session provider is present
                    from database.async_db import get_session
                    async with get_session() as session:
                        await self.crystallizer.evaluate_and_crystallize(session, symbol=symbol)
            except Exception as cry_err:
                logger.debug(f"[BackgroundReview] Crystallization check skipped or failed: {cry_err}")

        self.processed_count += 1
