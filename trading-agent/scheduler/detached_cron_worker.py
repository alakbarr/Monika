# ==============================================================================
# File: scheduler/detached_cron_worker.py
# ==============================================================================

"""
Detached Background Cron Scheduler Worker with Deliveries Database.
Institutional-grade engine turn protection architecture.

Runs independent background scheduled tasks (macro digests, symbol screening,
model fine-tune pipelines, system backups, equity monitoring) decoupled from the
trading agent main loop.
Maintains persistent schedule and delivery state in SQLite deliveries.db.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scheduler.cron_nlp_parser import parse_natural_schedule

logger = logging.getLogger("TradingAgent.Scheduler.DetachedCronWorker")

DEFAULT_DELIVERIES_DB_PATH = Path("trading-agent/data/deliveries.db")


class DetachedCronWorker:
    """Manages scheduled automation jobs with SQLite deliveries ledger."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DELIVERIES_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._running: bool = False
        self._worker_task: Optional[asyncio.Task] = None
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        conn = self.get_connection()
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    schedule_expr TEXT,
                    interval_seconds REAL,
                    handler_name TEXT NOT NULL,
                    payload_json TEXT,
                    target_platform TEXT,
                    target_channel TEXT,
                    last_run REAL,
                    next_run REAL,
                    is_active INTEGER DEFAULT 1,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_text TEXT,
                    delivered_at REAL NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(job_id) ON DELETE CASCADE
                );
            """)
        conn.close()

    def register_handler(self, name: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a callable handler function by name."""
        self._handlers[name] = handler
        logger.debug(f"[DetachedCronWorker] Registered handler '{name}'.")

    def add_job(
        self,
        job_id: str,
        name: str,
        schedule_text: str,
        handler_name: str,
        payload: Optional[Dict[str, Any]] = None,
        target_platform: Optional[str] = None,
        target_channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add and schedule a new job via natural language or cron expression."""
        cron_expr, interval_sec, desc = parse_natural_schedule(schedule_text)
        now = time.time()
        next_run = now + (interval_sec or 60.0)

        conn = self.get_connection()
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO scheduled_jobs (
                    job_id, name, schedule_expr, interval_seconds, handler_name,
                    payload_json, target_platform, target_channel, last_run, next_run,
                    is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
            """, (
                job_id,
                name,
                cron_expr,
                interval_sec,
                handler_name,
                json.dumps(payload or {}),
                target_platform,
                target_channel,
                None,
                next_run,
                now,
            ))
        conn.close()

        logger.info(f"[DetachedCronWorker] Added job '{job_id}' ({name}): {desc}, next_run in {int(next_run - now)}s")
        return {
            "job_id": job_id,
            "name": name,
            "description": desc,
            "next_run": next_run,
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM scheduled_jobs ORDER BY created_at DESC;")
        jobs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jobs

    def remove_job(self, job_id: str) -> bool:
        conn = self.get_connection()
        with conn:
            cursor = conn.execute("DELETE FROM scheduled_jobs WHERE job_id = ?;", (job_id,))
            deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    async def execute_job_now(self, job_id: str) -> Tuple[bool, str]:
        """Trigger an immediate run of a registered job."""
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM scheduled_jobs WHERE job_id = ?;", (job_id,))
        job = cursor.fetchone()
        if not job:
            conn.close()
            return False, f"Job '{job_id}' not found."

        handler_name = job["handler_name"]
        handler = self._handlers.get(handler_name)
        if not handler:
            conn.close()
            return False, f"Handler '{handler_name}' is not registered."

        payload = json.loads(job["payload_json"] or "{}")
        now = time.time()
        try:
            if inspect.iscoroutinefunction(handler):
                res = await handler(payload)
            else:
                res = handler(payload)
            output_str = str(res)
            status = "success"
            success = True
        except Exception as e:
            output_str = f"Error: {e}"
            status = "failed"
            success = False

        # Advance next run
        interval = job["interval_seconds"] or 3600.0
        next_run = now + interval

        with conn:
            conn.execute("""
                UPDATE scheduled_jobs 
                SET last_run = ?, next_run = ?
                WHERE job_id = ?;
            """, (now, next_run, job_id))

            conn.execute("""
                INSERT INTO job_deliveries (job_id, status, output_text, delivered_at)
                VALUES (?, ?, ?, ?);
            """, (job_id, status, output_str, now))

        conn.close()
        return success, output_str

    async def start(self) -> None:
        """Start the detached cron worker ticker loop."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._ticker_loop())
        logger.info("[DetachedCronWorker] Started cron background ticker loop.")

    async def stop(self) -> None:
        """Gracefully stop worker ticker loop."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("[DetachedCronWorker] Stopped cron background ticker loop.")

    async def _ticker_loop(self) -> None:
        """Poll and execute due jobs every 2 seconds."""
        while self._running:
            try:
                now = time.time()
                conn = self.get_connection()
                cursor = conn.execute("""
                    SELECT job_id FROM scheduled_jobs
                    WHERE is_active = 1 AND next_run <= ?;
                """, (now,))
                due_jobs = [row["job_id"] for row in cursor.fetchall()]
                conn.close()

                for j_id in due_jobs:
                    await self.execute_job_now(j_id)

                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DetachedCronWorker] Error in ticker tick: {e}", exc_info=True)
                await asyncio.sleep(5.0)
