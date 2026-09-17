"""
File: trading-agent/agent/monitors/paper_trade_monitor.py
Paper trading resolution and outcome monitoring loop.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("TradingAgent.PaperTradeMonitor")


async def run_paper_trade_monitor(agent: Any) -> None:
    """Dedicated loop to monitor and close paper trades based on price action."""
    check_interval_seconds = 300
    logger.info("Paper trade monitor started (interval: 5min)")

    while not agent.shutdown_event.is_set():
        try:
            from database.db import get_session
            from utils.analytics.paper_tracker import PaperTracker
            from utils.calibration.prescreen_calibrator import resolve_pending_prescreen_logs
            from utils.analytics.news_classification_tracker import resolve_pending_news_outcomes

            tracker = PaperTracker(agent.settings)
            async with get_session() as session:
                await resolve_pending_prescreen_logs(session)
                await resolve_pending_news_outcomes(session)
                closed = await tracker.check_and_close_trades(session)
                if closed:
                    logger.info(
                        f"[PaperMonitor] Closed {len(closed)} paper trades: "
                        + ", ".join([f"{t.get('symbol')} {t.get('exit_reason')}" for t in closed[:5]])
                    )

                    sched = getattr(agent, "cycle_scheduler", None)
                    if sched and hasattr(sched, "_update_adaptive_thresholds_realtime"):
                        await sched._update_adaptive_thresholds_realtime(session, closed)
        except Exception as e:
            logger.error(f"Paper trade monitor error (non-fatal): {e}")

        try:
            await asyncio.wait_for(agent.shutdown_event.wait(), timeout=check_interval_seconds)
        except asyncio.TimeoutError:
            pass
