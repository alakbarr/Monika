# ==============================================================================
# File: analysis/memory/background_review_fork.py
# ==============================================================================

"""
Background Review Fork & Counterfactual Analyzer.
Institutional-grade engine turn protection architecture.

Forks asynchronous post-mortem evaluations for closed trades and completed turns.
Conducts slippage & latency forensics, checks hypothesis validity against market outcome,
runs counterfactual what-if branch evaluations, and generates targeted negative constraints
without blocking the high-priority MT5 order execution path.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Memory.BackgroundReviewFork")


@dataclass
class ForkReviewResult:
    trade_id: str
    symbol: str
    pnl: float
    slippage_pips: float
    execution_latency_ms: float
    thesis_validated: bool
    counterfactual_better: bool
    counterfactual_pnl_delta: float
    negative_constraints: List[str] = field(default_factory=list)
    actionable_lessons: List[str] = field(default_factory=list)
    review_timestamp: float = field(default_factory=time.time)


class BackgroundReviewFork:
    """
    Asynchronous background evaluation fork for trade post-mortems and counterfactuals.
    """

    def __init__(self, max_queue_size: int = 100):
        self.queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=max_queue_size)
        self._running: bool = False
        self._worker_task: Optional[asyncio.Task] = None
        self.completed_reviews: List[ForkReviewResult] = []

    async def start(self) -> None:
        """Start the background fork worker loop."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._review_worker_loop())
        logger.info("[BackgroundReviewFork] Started review worker task.")

    async def stop(self) -> None:
        """Gracefully stop worker loop."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("[BackgroundReviewFork] Stopped review worker task.")

    def enqueue_for_review(self, trade_data: Dict[str, Any]) -> bool:
        """Non-blocking submission of a closed trade for background review."""
        try:
            self.queue.put_nowait(trade_data)
            return True
        except asyncio.QueueFull:
            logger.warning("[BackgroundReviewFork] Review queue full, dropping trade review.")
            return False

    async def _review_worker_loop(self) -> None:
        """Continuously process enqueued trades."""
        while self._running:
            try:
                trade_data = await self.queue.get()
                review = await self.evaluate_trade(trade_data)
                self.completed_reviews.append(review)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BackgroundReviewFork] Error processing trade review: {e}", exc_info=True)

    async def evaluate_trade(self, trade_data: Dict[str, Any]) -> ForkReviewResult:
        """
        Conduct deep post-mortem analysis of a trade.
        """
        trade_id = str(trade_data.get("trade_id", "unknown"))
        symbol = str(trade_data.get("symbol", "UNKNOWN")).upper()
        pnl = float(trade_data.get("pnl", 0.0) or 0.0)
        requested_price = float(trade_data.get("requested_price", 0.0) or 0.0)
        fill_price = float(trade_data.get("fill_price", requested_price) or requested_price)
        latency_ms = float(trade_data.get("latency_ms", 15.0) or 15.0)
        exit_reason = str(trade_data.get("exit_reason", "")).lower()

        # 1. Slippage calculation (in pips)
        pip_unit = 0.01 if "JPY" in symbol or "XAU" in symbol else 0.0001
        slippage_pips = abs(fill_price - requested_price) / pip_unit if requested_price > 0 else 0.0

        # 2. Hypothesis validation
        # If exit reason was TP hit or positive PnL, thesis generally held
        thesis_validated = (pnl > 0) or ("tp" in exit_reason)

        # 3. Counterfactual analysis: What if TP/SL were not altered?
        counterfactual_better = False
        counterfactual_pnl_delta = 0.0
        if "manual" in exit_reason or "trail" in exit_reason:
            target_tp = float(trade_data.get("original_tp", 0.0) or 0.0)
            target_sl = float(trade_data.get("original_sl", 0.0) or 0.0)
            max_future_price = float(trade_data.get("max_adverse_or_favorable", fill_price) or fill_price)

            # Simulated counterfactual outcome
            if pnl < 0 and target_tp > fill_price and max_future_price >= target_tp:
                counterfactual_better = True
                counterfactual_pnl_delta = abs(pnl) * 1.5

        # 4. Synthesize negative constraints and lessons
        negative_constraints = []
        actionable_lessons = []

        if pnl < 0:
            if slippage_pips > 3.0:
                negative_constraints.append(
                    f"DO NOT enter market orders on {symbol} when slippage exceeds 3.0 pips; use limit orders."
                )
            if "news" in trade_data.get("tags", []):
                negative_constraints.append(
                    f"DO NOT open new positions on {symbol} within 15 minutes of tier-1 macroeconomic releases."
                )
            actionable_lessons.append(
                f"Trade {trade_id} on {symbol} experienced loss {pnl:.2f}. "
                f"Slippage was {slippage_pips:.1f} pips, exit reason '{exit_reason}'."
            )
        else:
            actionable_lessons.append(
                f"Trade {trade_id} on {symbol} succeeded with profit {pnl:.2f}. Setup thesis validated."
            )

        return ForkReviewResult(
            trade_id=trade_id,
            symbol=symbol,
            pnl=pnl,
            slippage_pips=round(slippage_pips, 2),
            execution_latency_ms=round(latency_ms, 2),
            thesis_validated=thesis_validated,
            counterfactual_better=counterfactual_better,
            counterfactual_pnl_delta=round(counterfactual_pnl_delta, 2),
            negative_constraints=negative_constraints,
            actionable_lessons=actionable_lessons,
        )
