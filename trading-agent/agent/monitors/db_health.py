"""
File: trading-agent/agent/monitors/db_health.py
Database connection pool health monitoring.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("TradingAgent.DBHealth")


async def run_db_health_check(agent: Any) -> None:
    """Monitor Database connection pool health."""
    while not agent.shutdown_event.is_set():
        try:
            from database.db import engine
            from sqlalchemy import text

            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            try:
                from utils.infra.notifier import AgentNotifier

                await AgentNotifier().send_critical(
                    f"🚨 <b>CRITICAL: Database Health Check Failed!</b>\n"
                    f"PostgreSQL connection pool query <code>SELECT 1</code> error:\n"
                    f"<code>{e}</code>\n"
                    f"Trading operations may fail."
                )
            except Exception as notify_err:
                logger.debug(f"Failed to send DB health check alert: {notify_err}")

        try:
            await asyncio.wait_for(agent.shutdown_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass
