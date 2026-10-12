import asyncio
import json
import os
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from utils.clock import ensure_utc
from database.models import Base, SystemConfig, NewsItem
from scheduler.unified_cron_engine import UnifiedCronEngine
from scrapers.sentiment.fxssi_sentiment import FXSSISentimentFetcher
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select


def test_ensure_utc_helper():
    """Verify ensure_utc cleanly converts naive and aware datetimes to UTC."""
    assert ensure_utc(None) is None

    # Naive datetime
    naive = datetime(2026, 10, 9, 9, 58, 1)
    assert naive.tzinfo is None
    aware = ensure_utc(naive)
    assert aware is not None
    assert aware.tzinfo == timezone.utc
    assert aware.year == 2026
    assert aware.hour == 9

    # Aware datetime in non-UTC timezone (+07:00)
    tz_plus_7 = timezone(timedelta(hours=7))
    dt_p7 = datetime(2026, 10, 9, 16, 58, 1, tzinfo=tz_plus_7)
    converted = ensure_utc(dt_p7)
    assert converted is not None
    assert converted.tzinfo == timezone.utc
    assert converted.hour == 9  # 16:58 +7 is 09:58 UTC

    # Subtraction between now_utc and ensure_utc(naive) must never raise TypeError
    now_utc = datetime.now(timezone.utc)
    diff = (now_utc - ensure_utc(naive)).total_seconds()
    assert isinstance(diff, float)


def test_unified_cron_engine_migrates_legacy_schema_without_pending_slot(tmp_path):
    """
    Reproduces Issue 1:
    Legacy cron_jobs table lacking pending_slot, name, target_destination, etc.
    UnifiedCronEngine._init_db must automatically migrate missing columns
    so _evaluate_due_jobs() runs without OperationalError: no such column: pending_slot.
    """
    db_file = tmp_path / "legacy_cron.db"
    conn = sqlite3.connect(str(db_file))
    # Create the old legacy schema from earlier Monika version
    conn.execute("""
        CREATE TABLE cron_jobs (
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
    # Insert a due job under legacy schema
    conn.execute("""
        INSERT INTO cron_jobs (
            job_id, schedule_expression, prompt, target_delivery,
            next_run_at, is_active, no_agent
        ) VALUES ('job_legacy_1', 'every 1 minute', 'echo test', 'log', 100.0, 1, 1)
    """)
    conn.commit()
    conn.close()

    # Initializing UnifiedCronEngine must automatically detect and add missing columns
    engine = UnifiedCronEngine(db_path=str(db_file), tick_interval_seconds=1.0)
    
    # Verify columns were migrated
    conn = sqlite3.connect(str(db_file))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()]
    conn.close()

    assert "pending_slot" in cols
    assert "name" in cols
    assert "target_destination" in cols
    assert "last_output" in cols
    assert "timeout_seconds" in cols

    # _evaluate_due_jobs must execute cleanly without 'no such column: pending_slot'
    executed_jobs = []
    engine.register_execution_callback(lambda job: executed_jobs.append(job.job_id))
    engine._evaluate_due_jobs()

    assert len(executed_jobs) == 1
    assert executed_jobs[0] == "job_legacy_1"


def test_fxssi_sentiment_fetch_clean_read_phase_order():
    """
    Verifies Issue 3 fix:
    Both select queries (for cfg_key and hist_key) must be executed in the
    read phase BEFORE any mutation to existing.value or self.session.add occurs,
    guaranteeing that Query-invoked autoflush is impossible.
    """
    import inspect
    from scrapers.sentiment.fxssi_sentiment import FXSSISentimentFetcher

    source = inspect.getsource(FXSSISentimentFetcher.fetch)
    pos_select_cfg = source.find("select(SystemConfig).where(SystemConfig.key == cfg_key)")
    pos_select_hist = source.find("select(SystemConfig).where(SystemConfig.key == hist_key)")
    pos_mutate_existing = source.find("existing.value = json.dumps(result)")

    assert pos_select_cfg != -1, "Query for cfg_key missing"
    assert pos_select_hist != -1, "Query for hist_key missing"
    assert pos_mutate_existing != -1, "Mutation for existing missing"

    # Both select queries must precede mutation
    assert pos_select_cfg < pos_mutate_existing, "cfg_key select must precede mutation"
    assert pos_select_hist < pos_mutate_existing, "hist_key select must precede mutation to avoid autoflush"
