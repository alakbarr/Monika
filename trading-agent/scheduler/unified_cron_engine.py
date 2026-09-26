# ==============================================================================
# File: scheduler/unified_cron_engine.py
# ==============================================================================

"""
Unified Cron Engine & Autonomous Task Orchestrator for Monika.
Combines at-most-once invariant execution, natural language schedule expressions,
trading market session presets, zero-cost monitor hashing (token suppression),
and multi-channel dispatch delivery (CLI, Telegram, Discord, Webhook, Log).
"""

from __future__ import annotations

import asyncio
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

from scheduler.cron_nlp_parser import MARKET_SESSIONS_UTC, parse_natural_schedule

logger = logging.getLogger("TradingAgent.Scheduler.UnifiedCronEngine")

DEFAULT_CRON_DB = "data/universal_cron.db"

# Safety blocklist against destructive host commands in scheduled tasks
_ANTI_SUICIDE_PATTERNS = [
    re.compile(r"\brm\s+-(?:r|f|rf|fr)\s+(?:/|~|\$HOME|trading-agent|\*)", re.IGNORECASE),
    re.compile(r"\bdel\s+/[fs]\s+c:\\", re.IGNORECASE),
    re.compile(r"\bkill\s+-9\s+-1\b|\bkillall\b|\btaskkill\s+/[fF]\s+.*python", re.IGNORECASE),
    re.compile(r"\b(format|mkfs)\s+[a-z]:|\b(shutdown|reboot|poweroff|halt)\b", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|\:&\s*\};:", re.IGNORECASE),
]


@dataclass
class UnifiedCronJob:
    """Unified schema for scheduled background recurring tasks and one-shots."""
    job_id: str
    schedule_expression: str
    prompt: str
    name: str = ""
    target_delivery: str = "session"  # 'session', 'telegram', 'discord', 'webhook', 'cli', 'log'
    target_destination: Optional[str] = None  # chat_id, webhook_url, or channel
    workdir: Optional[str] = None
    monitor_script: Optional[str] = None
    last_monitor_hash: Optional[str] = None
    next_run_at: float = 0.0
    last_run_at: Optional[float] = None
    last_exit_code: Optional[int] = None
    last_output: Optional[str] = None
    is_active: bool = True
    no_agent: bool = False
    pending_slot: bool = False
    timeout_seconds: float = 300.0
    metadata: Dict[str, Any] = field(default_factory=dict)


def compute_next_cron_timestamp(cron_expr: str, from_ts: Optional[float] = None) -> float:
    """
    Computes next execution epoch timestamp for a standard 5-part cron expression.
    Format: 'minute hour day_of_month month day_of_week' (0-6 Sunday to Saturday, or 1-5 Mon-Fri).
    Uses lightweight forward scanning up to 366 days.
    """
    base_ts = from_ts or time.time()
    dt = datetime.datetime.fromtimestamp(base_ts, tz=datetime.timezone.utc)
    # Start looking from the next whole minute
    dt = dt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        # Fallback to 1 hour if expression is malformed
        return base_ts + 3600.0

    min_part, hour_part, dom_part, month_part, dow_part = parts

    def _matches_field(val: int, pattern: str, is_dow: bool = False) -> bool:
        if pattern == "*":
            return True
        if pattern.startswith("*/"):
            step = int(pattern[2:])
            return (val % step) == 0
        if "," in pattern:
            subparts = pattern.split(",")
            return any(_matches_field(val, sp, is_dow) for sp in subparts)
        if "-" in pattern:
            low, high = map(int, pattern.split("-"))
            return low <= val <= high
        # Direct number match
        target = int(pattern)
        if is_dow and target == 7:
            target = 0  # 7 represents Sunday in some systems
        return val == target

    # Forward search up to 525,600 minutes (1 year)
    max_minutes = 60 * 24 * 366
    for _ in range(max_minutes):
        iso_dow = dt.isoweekday()  # 1 (Monday) to 7 (Sunday)
        dow_0_based = 0 if iso_dow == 7 else iso_dow  # 0 is Sunday, 1 is Monday ... 6 is Saturday

        if (
            _matches_field(dt.month, month_part)
            and _matches_field(dt.day, dom_part)
            and (_matches_field(iso_dow, dow_part, is_dow=True) or _matches_field(dow_0_based, dow_part, is_dow=True))
            and _matches_field(dt.hour, hour_part)
            and _matches_field(dt.minute, min_part)
        ):
            return dt.timestamp()

        dt += datetime.timedelta(minutes=1)

    return base_ts + 3600.0


class UnifiedCronEngine:
    """
    Centralized Cron Engine unifying natural language scheduling,
    market session triggers, at-most-once execution guarantees,
    token-saving output hashing, and multi-channel result dispatch.
    """

    def __init__(self, db_path: str = DEFAULT_CRON_DB, tick_interval_seconds: float = 15.0):
        self.db_path = db_path
        self.tick_interval_seconds = tick_interval_seconds
        self._lock = threading.Lock()
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._execution_callbacks: List[Callable[[UnifiedCronJob], None]] = []
        self._running_jobs: Dict[str, float] = {}
        self._channel_dispatcher: Optional[Callable[[UnifiedCronJob, str], None]] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite WAL database for persistent job registry."""
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    job_id TEXT PRIMARY KEY,
                    name TEXT,
                    schedule_expression TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    target_delivery TEXT NOT NULL,
                    target_destination TEXT,
                    workdir TEXT,
                    monitor_script TEXT,
                    last_monitor_hash TEXT,
                    next_run_at REAL NOT NULL,
                    last_run_at REAL,
                    last_exit_code INTEGER,
                    last_output TEXT,
                    is_active INTEGER DEFAULT 1,
                    no_agent INTEGER DEFAULT 0,
                    pending_slot INTEGER DEFAULT 0,
                    timeout_seconds REAL DEFAULT 300.0,
                    metadata_json TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def parse_schedule_expression(self, expr: str, from_timestamp: Optional[float] = None) -> Tuple[float, str]:
        """
        Parses schedule expression into (next_run_epoch, resolved_description).
        Supports:
          1. Relative durations ('30s', '15m', '2h', '1d')
          2. Natural language phrases ('every 5 minutes', 'hourly', 'every weekday at 08:30')
          3. Market session presets ('london_open', 'ny_open', 'tokyo_open', 'daily_close')
          4. 5-part cron expressions ('0 9 * * 1-5', '*/15 * * * *')
        """
        now = from_timestamp or time.time()
        expr_clean = expr.strip()

        # 1. Simple relative durations
        rel_match = re.match(r"^(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", expr_clean, re.IGNORECASE)
        if rel_match:
            val = int(rel_match.group(1))
            unit = rel_match.group(2).lower()
            multipliers = {
                "s": 1, "sec": 1,
                "m": 60, "min": 60,
                "h": 3600, "hr": 3600,
                "d": 86400, "day": 86400,
            }
            sec_delta = val * multipliers.get(unit, 60)
            return now + sec_delta, f"Interval: {val} {unit}"

        # 2. NLP and Market presets via cron_nlp_parser
        cron_expr, interval_sec, description = parse_natural_schedule(expr_clean)

        if interval_sec is not None:
            return now + interval_sec, description

        if cron_expr is not None:
            next_ts = compute_next_cron_timestamp(cron_expr, from_ts=now)
            return next_ts, description

        # Fallback default: 1 hour
        logger.warning(f"[UnifiedCronEngine] Unrecognized schedule '{expr}', defaulting to 1 hour.")
        return now + 3600.0, "Fallback 1 hour interval"

    def register_job(
        self,
        job_id: str,
        schedule_expression: str,
        prompt: str,
        name: str = "",
        target_delivery: str = "session",
        target_destination: Optional[str] = None,
        workdir: Optional[str] = None,
        monitor_script: Optional[str] = None,
        no_agent: bool = False,
        timeout_seconds: float = 300.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UnifiedCronJob:
        """
        Registers a new background job with safety checks and at-most-once semantics.
        """
        # Validate destructive patterns
        for pat in _ANTI_SUICIDE_PATTERNS:
            if pat.search(prompt):
                logger.error(f"[UnifiedCronEngine] Job '{job_id}' rejected: prompt matches destructive pattern.")
                raise ValueError("Prohibited destructive pattern detected in prompt.")
            if monitor_script and pat.search(monitor_script):
                logger.error(f"[UnifiedCronEngine] Job '{job_id}' rejected: monitor_script matches destructive pattern.")
                raise ValueError("Prohibited destructive pattern detected in monitor script.")

        next_run, desc = self.parse_schedule_expression(schedule_expression)

        job = UnifiedCronJob(
            job_id=job_id,
            name=name or job_id,
            schedule_expression=schedule_expression,
            prompt=prompt,
            target_delivery=target_delivery,
            target_destination=target_destination,
            workdir=workdir,
            monitor_script=monitor_script,
            next_run_at=next_run,
            is_active=True,
            no_agent=no_agent,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
        )

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cron_jobs (
                        job_id, name, schedule_expression, prompt, target_delivery,
                        target_destination, workdir, monitor_script, last_monitor_hash,
                        next_run_at, last_run_at, last_exit_code, last_output, is_active,
                        no_agent, pending_slot, timeout_seconds, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.name,
                        job.schedule_expression,
                        job.prompt,
                        job.target_delivery,
                        job.target_destination,
                        job.workdir,
                        job.monitor_script,
                        job.last_monitor_hash,
                        job.next_run_at,
                        job.last_run_at,
                        job.last_exit_code,
                        job.last_output,
                        1 if job.is_active else 0,
                        1 if job.no_agent else 0,
                        0,
                        job.timeout_seconds,
                        json.dumps(job.metadata),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(
            f"[UnifiedCronEngine] Registered job '{job_id}' ({desc}) -> Next run at "
            f"{datetime.datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        return job

    def unregister_job(self, job_id: str) -> bool:
        """Deletes a job from the database."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cron_jobs WHERE job_id = ?", (job_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
                return deleted
            finally:
                conn.close()

    def get_job(self, job_id: str) -> Optional[UnifiedCronJob]:
        """Retrieves a job by its unique ID."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM cron_jobs WHERE job_id = ?", (job_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_job(row)
            finally:
                conn.close()

    def list_jobs(self, active_only: bool = False) -> List[UnifiedCronJob]:
        """Lists all registered jobs."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                query = "SELECT * FROM cron_jobs"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY next_run_at ASC"
                cursor.execute(query)
                return [self._row_to_job(r) for r in cursor.fetchall()]
            finally:
                conn.close()

    def register_execution_callback(self, cb: Callable[[UnifiedCronJob], None]) -> None:
        """Registers a runner callback function for executing scheduled jobs."""
        self._execution_callbacks.append(cb)

    def set_channel_dispatcher(self, dispatcher: Callable[[UnifiedCronJob, str], None]) -> None:
        """Sets the multi-channel notification dispatcher for delivery results."""
        self._channel_dispatcher = dispatcher

    def start(self) -> None:
        """Starts the background scheduler tick thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._worker_thread = threading.Thread(target=self._tick_loop, daemon=True, name="UnifiedCronTick")
            self._worker_thread.start()
        logger.info("[UnifiedCronEngine] Engine background ticker started.")

    def stop(self) -> None:
        """Stops the background scheduler thread."""
        with self._lock:
            self._is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        logger.info("[UnifiedCronEngine] Engine background ticker stopped.")

    def close(self) -> None:
        """Closes workers and checkpoints WAL database."""
        self.stop()
        if self.db_path != ":memory:" and os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
            except Exception:
                pass

    def _tick_loop(self) -> None:
        """Main periodic evaluation loop."""
        while self._is_running:
            try:
                self._evaluate_due_jobs()
                self.check_hung_jobs()
            except Exception as exc:
                logger.error(f"[UnifiedCronEngine] Error in tick loop: {exc}", exc_info=True)
            time.sleep(self.tick_interval_seconds)

    def _evaluate_due_jobs(self) -> None:
        """
        Finds due jobs and dispatches them under the strict At-Most-Once invariant:
        Updates next_run_at and sets pending_slot=1 in DB BEFORE dispatching.
        """
        now = time.time()
        due_jobs: List[UnifiedCronJob] = []

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM cron_jobs WHERE is_active = 1 AND pending_slot = 0 AND next_run_at <= ?",
                    (now,),
                )
                rows = cursor.fetchall()

                for row in rows:
                    job = self._row_to_job(row)
                    # Advance next_run_at in DB before dispatching to eliminate duplicate runs
                    next_timestamp, _ = self.parse_schedule_expression(job.schedule_expression, from_timestamp=now)
                    cursor.execute(
                        """
                        UPDATE cron_jobs
                        SET next_run_at = ?, last_run_at = ?, pending_slot = 1
                        WHERE job_id = ?
                        """,
                        (next_timestamp, now, job.job_id),
                    )
                    due_jobs.append(job)

                conn.commit()
            finally:
                conn.close()

        # Dispatch due jobs
        for job in due_jobs:
            self._dispatch_job(job)

    def _dispatch_job(self, job: UnifiedCronJob) -> None:
        """
        Evaluates zero-cost monitor output hashing, then triggers execution callbacks.
        """
        # 1. Zero-Cost Token Suppression check
        if job.monitor_script:
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
                        f"[UnifiedCronEngine] Output hash unchanged for job '{job.job_id}'. "
                        "Skipping execution to suppress unnecessary token consumption."
                    )
                    self._release_pending_slot(job.job_id, exit_code=0, output="Skipped: Monitor hash unchanged.")
                    return

                # Record newly changed monitor hash
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
                logger.warning(f"[UnifiedCronEngine] Monitor script check failed for '{job.job_id}': {exc}")

        # 2. Track running status for watchdog
        self._running_jobs[job.job_id] = time.time()
        logger.info(f"[UnifiedCronEngine] Executing job '{job.job_id}' (Delivery: {job.target_delivery})")

        execution_output = ""
        exit_code = 0
        try:
            # If no callbacks, execute default isolated script runner if no_agent is set
            if not self._execution_callbacks and job.no_agent and job.prompt:
                shell = ["powershell.exe", "-NoProfile", "-Command"] if sys.platform == "win32" else ["/bin/bash", "-c"]
                res = subprocess.run(
                    shell + [job.prompt],
                    cwd=job.workdir or os.getcwd(),
                    capture_output=True,
                    text=True,
                    timeout=job.timeout_seconds,
                )
                exit_code = res.returncode
                execution_output = res.stdout if exit_code == 0 else f"{res.stdout}\n[ERROR]: {res.stderr}"
            else:
                for cb in self._execution_callbacks:
                    try:
                        cb(job)
                    except Exception as cb_exc:
                        logger.error(f"[UnifiedCronEngine] Callback execution error for '{job.job_id}': {cb_exc}")
                        exit_code = 1
                        execution_output = str(cb_exc)

            # Dispatch result to requested channel if configured
            if self._channel_dispatcher and execution_output:
                try:
                    self._channel_dispatcher(job, execution_output)
                except Exception as dist_exc:
                    logger.warning(f"[UnifiedCronEngine] Result dispatch error: {dist_exc}")

        finally:
            self._running_jobs.pop(job.job_id, None)
            self._release_pending_slot(job.job_id, exit_code=exit_code, output=execution_output)

    def _release_pending_slot(self, job_id: str, exit_code: int = 0, output: Optional[str] = None) -> None:
        """Releases pending lock and updates execution status in DB."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    UPDATE cron_jobs
                    SET pending_slot = 0, last_exit_code = ?, last_output = ?
                    WHERE job_id = ?
                    """,
                    (exit_code, output, job_id),
                )
                conn.commit()
            except Exception as exc:
                logger.error(f"[UnifiedCronEngine] Failed releasing pending slot for '{job_id}': {exc}")
            finally:
                conn.close()

    def check_hung_jobs(self, max_runtime_sec: float = 600.0) -> List[str]:
        """
        Watchdog: Scans running jobs exceeding max_runtime_sec.
        Evicts them from tracking and marks timeout exit code (-1) in database.
        """
        now = time.time()
        hung_jobs: List[str] = []

        with self._lock:
            for job_id, start_time in list(self._running_jobs.items()):
                if now - start_time > max_runtime_sec:
                    hung_jobs.append(job_id)
                    logger.warning(
                        f"[UnifiedCronWatchdog] Job '{job_id}' hung (running for {now - start_time:.1f}s > {max_runtime_sec}s). "
                        "Evicting and recording timeout."
                    )
                    self._running_jobs.pop(job_id, None)

            if hung_jobs:
                try:
                    conn = sqlite3.connect(self.db_path)
                    for jid in hung_jobs:
                        conn.execute(
                            "UPDATE cron_jobs SET pending_slot = 0, last_exit_code = -1, last_output = 'Job timed out by watchdog' WHERE job_id = ?",
                            (jid,),
                        )
                    conn.commit()
                    conn.close()
                except Exception as exc:
                    logger.error(f"[UnifiedCronWatchdog] Failed updating hung jobs status: {exc}")

        return hung_jobs

    def _row_to_job(self, row: Tuple[Any, ...]) -> UnifiedCronJob:
        """Converts raw SQLite row into UnifiedCronJob dataclass instance."""
        return UnifiedCronJob(
            job_id=row[0],
            name=row[1] or row[0],
            schedule_expression=row[2],
            prompt=row[3],
            target_delivery=row[4],
            target_destination=row[5],
            workdir=row[6],
            monitor_script=row[7],
            last_monitor_hash=row[8],
            next_run_at=row[9],
            last_run_at=row[10],
            last_exit_code=row[11],
            last_output=row[12],
            is_active=bool(row[13]),
            no_agent=bool(row[14]),
            pending_slot=bool(row[15]),
            timeout_seconds=float(row[16]) if row[16] else 300.0,
            metadata=json.loads(row[17]) if row[17] else {},
        )


# Global singleton instance
_GLOBAL_CRON_ENGINE: Optional[UnifiedCronEngine] = None


def get_unified_cron_engine(db_path: str = DEFAULT_CRON_DB) -> UnifiedCronEngine:
    """Returns global singleton UnifiedCronEngine instance."""
    global _GLOBAL_CRON_ENGINE
    if _GLOBAL_CRON_ENGINE is None:
        _GLOBAL_CRON_ENGINE = UnifiedCronEngine(db_path=db_path)
    return _GLOBAL_CRON_ENGINE


# Backward Compatibility Alias
CronJob = UnifiedCronJob
UniversalCronScheduler = UnifiedCronEngine
