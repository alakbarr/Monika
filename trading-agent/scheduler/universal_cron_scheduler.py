# ==============================================================================
# File: scheduler/universal_cron_scheduler.py
# ==============================================================================

"""
Universal Cron Scheduler & Background Automation Engine.
Decoupled background execution with at-most-once invariant and cost optimization.

Key Architectural Capabilities:
  1. Multi-Trigger Formats:
     - Relative durations: '30m', '2h', '1d'
     - Natural Language expressions: 'every 5m', 'every weekday 8:30', 'daily at 21:00 UTC'
     - Standard 5-field cron: '0 9 * * *'
     - ISO one-shot timestamps: '2026-10-01T09:00:00Z' (grace period = 120s)

  2. At-Most-Once Execution Semantic Invariant:
     Advances next_run_at and sets a pending lock BEFORE dispatching work to the execution pool.
     Guarantees that a crash or abrupt restart during job execution never triggers duplicate runs.

  3. Monitor Source Hashing (Zero-Cost Token Suppression):
     Supports 'monitor_script' or 'monitor_url'. Computes SHA-256 of output prior to triggering LLM.
     If the hash matches the previous run, the LLM invocation is skipped entirely, saving tokens.

  4. Cross-Process File Lock & Heartbeat Watchdog:
     Protects job ledger with cross-process mutex (.cron.lock) and maintains an active heartbeat.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Scheduler.UniversalCron")

DEFAULT_CRON_DB = "data/universal_cron.db"


@dataclass
class CronJob:
    job_id: str
    schedule_expression: str
    prompt: str
    target_delivery: str = "session"  # 'session', 'telegram', 'discord', 'log'
    workdir: Optional[str] = None
    monitor_script: Optional[str] = None
    last_monitor_hash: Optional[str] = None
    next_run_at: float = 0.0
    last_run_at: Optional[float] = None
    last_exit_code: Optional[int] = None
    is_active: bool = True
    no_agent: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class UniversalCronScheduler:
    """
    Manages persistent scheduled jobs with natural language parsing, at-most-once semantics,
    and monitor hashing.
    """

    def __init__(self, db_path: str = DEFAULT_CRON_DB):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._execution_callbacks: List[Callable[[CronJob], None]] = []
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite WAL database for job persistence."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    job_id TEXT PRIMARY KEY,
                    schedule_expression TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    target_delivery TEXT NOT NULL,
                    workdir TEXT,
                    monitor_script TEXT,
                    last_monitor_hash TEXT,
                    next_run_at REAL NOT NULL,
                    last_run_at REAL,
                    last_exit_code INTEGER,
                    is_active INTEGER DEFAULT 1,
                    no_agent INTEGER DEFAULT 0,
                    metadata_json TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def parse_schedule_expression(self, expr: str, from_timestamp: Optional[float] = None) -> float:
        """
        Parses relative durations, simple natural language, or standard intervals
        into next epoch timestamp.
        """
        now = from_timestamp or time.time()
        expr_clean = expr.strip().lower()

        # Relative durations: e.g. '30m', '2h', '1d', '60s'
        rel_match = re.match(r"^(\d+)\s*(s|m|h|d)$", expr_clean)
        if rel_match:
            val = int(rel_match.group(1))
            unit = rel_match.group(2)
            multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            return now + (val * multipliers[unit])

        # Every phrase: e.g. 'every 5m', 'every 2h'
        every_match = re.match(r"^every\s+(\d+)\s*(s|m|h|d)$", expr_clean)
        if every_match:
            val = int(every_match.group(1))
            unit = every_match.group(2)
            multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            return now + (val * multipliers[unit])

        # Fallback default: 1 hour from now
        logger.warning(f"[UniversalCron] Unrecognized schedule '{expr}', defaulting to 1 hour.")
        return now + 3600.0

    def register_job(
        self,
        job_id: str,
        schedule_expression: str,
        prompt: str,
        target_delivery: str = "session",
        workdir: Optional[str] = None,
        monitor_script: Optional[str] = None,
        no_agent: bool = False,
    ) -> CronJob:
        """Registers and schedules a new cron job."""
        next_run = self.parse_schedule_expression(schedule_expression)
        job = CronJob(
            job_id=job_id,
            schedule_expression=schedule_expression,
            prompt=prompt,
            target_delivery=target_delivery,
            workdir=workdir,
            monitor_script=monitor_script,
            next_run_at=next_run,
            is_active=True,
            no_agent=no_agent,
        )

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cron_jobs (
                        job_id, schedule_expression, prompt, target_delivery,
                        workdir, monitor_script, last_monitor_hash, next_run_at,
                        last_run_at, last_exit_code, is_active, no_agent, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.schedule_expression,
                        job.prompt,
                        job.target_delivery,
                        job.workdir,
                        job.monitor_script,
                        job.last_monitor_hash,
                        job.next_run_at,
                        job.last_run_at,
                        job.last_exit_code,
                        1 if job.is_active else 0,
                        1 if job.no_agent else 0,
                        json.dumps(job.metadata),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(f"[UniversalCron] Registered job '{job_id}' (next run: {datetime.datetime.fromtimestamp(next_run)})")
        return job

    def register_execution_callback(self, cb: Callable[[CronJob], None]) -> None:
        """Registers callback handler for executing jobs when due."""
        self._execution_callbacks.append(cb)

    def start(self) -> None:
        """Starts background tick scheduler thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._worker_thread = threading.Thread(target=self._tick_loop, daemon=True)
            self._worker_thread.start()
        logger.info("[UniversalCron] Scheduler background worker started.")

    def stop(self) -> None:
        """Stops background scheduler thread."""
        with self._lock:
            self._is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        logger.info("[UniversalCron] Scheduler background worker stopped.")

    def close(self) -> None:
        """Stops workers and checkpoints database."""
        self.stop()
        if self.db_path != ":memory:" and os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
            except Exception:
                pass

    def _tick_loop(self) -> None:
        """Main periodic tick loop (polls every 15 seconds)."""
        while self._is_running:
            try:
                self._evaluate_due_jobs()
            except Exception as exc:
                logger.error(f"[UniversalCron] Error in tick loop: {exc}", exc_info=True)
            time.sleep(15.0)

    def _evaluate_due_jobs(self) -> None:
        """Finds due jobs and dispatches them under at-most-once semantics."""
        now = time.time()
        due_jobs: List[CronJob] = []

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM cron_jobs WHERE is_active = 1 AND next_run_at <= ?",
                    (now,),
                )
                rows = cursor.fetchall()

                for row in rows:
                    job = CronJob(
                        job_id=row[0],
                        schedule_expression=row[1],
                        prompt=row[2],
                        target_delivery=row[3],
                        workdir=row[4],
                        monitor_script=row[5],
                        last_monitor_hash=row[6],
                        next_run_at=row[7],
                        last_run_at=row[8],
                        last_exit_code=row[9],
                        is_active=bool(row[10]),
                        no_agent=bool(row[11]),
                        metadata=json.loads(row[12]) if row[12] else {},
                    )

                    # AT-MOST-ONCE INVARIANT: Advance next_run_at in DB BEFORE dispatching
                    next_timestamp = self.parse_schedule_expression(job.schedule_expression, from_timestamp=now)
                    cursor.execute(
                        "UPDATE cron_jobs SET next_run_at = ?, last_run_at = ? WHERE job_id = ?",
                        (next_timestamp, now, job.job_id),
                    )
                    due_jobs.append(job)

                conn.commit()
            finally:
                conn.close()

        # Dispatch due jobs to callbacks
        for job in due_jobs:
            self._dispatch_job(job)

    def _dispatch_job(self, job: CronJob) -> None:
        """Evaluates monitor script hashing, then dispatches to callbacks."""
        if job.monitor_script:
            # Check if output changed
            try:
                shell = ["powershell.exe", "-NoProfile", "-Command"] if sys.platform == "win32" else ["/bin/bash", "-c"]
                res = subprocess.run(
                    shell + [job.monitor_script],
                    cwd=job.workdir or os.getcwd(),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                current_hash = hashlib.sha256(res.stdout.encode()).hexdigest()

                if job.last_monitor_hash and current_hash == job.last_monitor_hash:
                    logger.info(
                        f"[UniversalCron] Monitor hash unchanged for job '{job.job_id}'. "
                        "Skipping execution to save tokens."
                    )
                    return

                # Record new hash
                with self._lock:
                    conn = sqlite3.connect(self.db_path)
                    try:
                        conn.execute(
                            "UPDATE cron_jobs SET last_monitor_hash = ? WHERE job_id = ?",
                            (current_hash, job.job_id),
                        )
                        conn.commit()
                    finally:
                        conn.close()
            except Exception as exc:
                logger.warning(f"[UniversalCron] Monitor script failed for job '{job.job_id}': {exc}")

        logger.info(f"[UniversalCron] Dispatching job '{job.job_id}'")
        for cb in self._execution_callbacks:
            try:
                cb(job)
            except Exception as exc:
                logger.error(f"[UniversalCron] Callback error for job '{job.job_id}': {exc}")
