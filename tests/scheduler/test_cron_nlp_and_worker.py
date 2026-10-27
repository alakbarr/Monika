# ==============================================================================
# File: tests/scheduler/test_phase6_cron_nlp_and_worker.py
# ==============================================================================

"""
Unit Test Suite for Phase 6:
Natural Language Schedule Parser and Detached Background Cron Worker with deliveries.db.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest

from monika.application.scheduler.cron_nlp_parser import parse_natural_schedule
from monika.application.scheduler.detached_cron_worker import DetachedCronWorker


# ==============================================================================
# 1. Cron NLP Parser Tests
# ==============================================================================


def test_cron_nlp_parser_expressions():
    # Minute intervals
    expr1, sec1, desc1 = parse_natural_schedule("every 5 minutes")
    assert expr1 == "*/5 * * * *"
    assert sec1 is None
    assert "Every 5 minutes" in desc1

    # Seconds interval
    expr2, sec2, desc2 = parse_natural_schedule("every 30 seconds")
    assert expr2 is None
    assert sec2 == 30.0
    assert "Every 30 seconds" in desc2

    # Daily at specific time
    expr3, sec3, desc3 = parse_natural_schedule("daily at 21:45")
    assert expr3 == "45 21 * * *"
    assert sec3 is None
    assert "21:45" in desc3

    # Weekday at specific time
    expr4, sec4, desc4 = parse_natural_schedule("every weekday at 08:30")
    assert expr4 == "30 8 * * 1-5"
    assert sec4 is None

    # Trading session preset
    expr5, sec5, desc5 = parse_natural_schedule("london open")
    assert expr5 == "0 8 * * 1-5"
    assert "London Session Open" in desc5

    # Direct 5-field cron pass-through
    raw_cron = "*/15 9-17 * * 1-5"
    expr6, sec6, desc6 = parse_natural_schedule(raw_cron)
    assert expr6 == raw_cron


def test_cron_nlp_parser_fail_closed_on_unrecognized():
    """Verify parse_natural_schedule fails closed (returns None, None, ...) for unparseable input."""
    # Unparseable words or typos must not default to 1-hour interval
    expr, sec, desc = parse_natural_schedule("test")
    assert expr is None
    assert sec is None
    assert "Unrecognized schedule" in desc

    expr_random, sec_random, desc_random = parse_natural_schedule("random garbage string xyz")
    assert expr_random is None
    assert sec_random is None
    assert "Unrecognized schedule" in desc_random


def test_unified_cron_rejects_unparseable_schedule(tmp_path):
    """Verify UnifiedCronEngine.register_job raises ValueError when given an unparseable expression."""
    from monika.application.scheduler.unified_cron_engine import UnifiedCronEngine

    db_path = str(tmp_path / "cron_test.db")
    engine = UnifiedCronEngine(db_path=db_path)

    with pytest.raises(ValueError, match="Unrecognized or invalid schedule expression"):
        engine.register_job(
            job_id="bad_job",
            schedule_expression="test",
            prompt="do something",
        )


def test_unified_cron_deactivates_legacy_unparseable_due_job(tmp_path):
    """Verify UnifiedCronEngine._evaluate_due_jobs deactivates (is_active=0) legacy jobs with corrupted schedule expressions."""
    import sqlite3
    import time
    from monika.application.scheduler.unified_cron_engine import UnifiedCronEngine

    db_path = str(tmp_path / "cron_test.db")
    engine = UnifiedCronEngine(db_path=db_path)

    # Insert a raw corrupted job directly into sqlite
    now = time.time()
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO cron_jobs (
                job_id, name, schedule_expression, prompt, target_delivery,
                target_destination, is_active, pending_slot, next_run_at, timeout_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, 300.0)
            """,
            ("corrupt_job", "corrupt_job", "test", "dummy prompt", "session", None, now - 10),
        )

    # Trigger evaluation
    engine._evaluate_due_jobs()

    # Verify that the job was deactivated and NOT dispatched
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT is_active, last_output FROM cron_jobs WHERE job_id = 'corrupt_job'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 0  # is_active should be 0
        assert "Deactivated due to invalid schedule expression" in row[1]


# ==============================================================================
# 2. Detached Cron Worker Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_detached_cron_worker_lifecycle_and_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_deliveries.db"
        worker = DetachedCronWorker(db_path)

        # Register a mock job handler
        execution_log = []

        def mock_macro_digest(payload: dict) -> str:
            msg = f"Generated macro brief for {payload.get('symbol', 'ALL')}"
            execution_log.append(msg)
            return msg

        worker.register_handler("macro_digest", mock_macro_digest)

        # 1. Add job
        job_info = worker.add_job(
            job_id="job_macro_morning",
            name="Morning Macro Briefing",
            schedule_text="every 60 seconds",
            handler_name="macro_digest",
            payload={"symbol": "XAUUSD"},
            target_platform="telegram",
            target_channel="admin_chat",
        )
        assert job_info["job_id"] == "job_macro_morning"

        # 2. List jobs
        jobs = worker.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["name"] == "Morning Macro Briefing"
        assert jobs[0]["handler_name"] == "macro_digest"

        # 3. Execute immediately
        success, output = await worker.execute_job_now("job_macro_morning")
        assert success
        assert "Generated macro brief for XAUUSD" in output
        assert len(execution_log) == 1

        # Verify deliveries ledger record
        conn = worker.get_connection()
        cursor = conn.execute("SELECT * FROM job_deliveries WHERE job_id = 'job_macro_morning';")
        deliveries = cursor.fetchall()
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "success"
        assert "Generated macro brief" in deliveries[0]["output_text"]
        conn.close()

        # 4. Remove job
        assert worker.remove_job("job_macro_morning")
        assert len(worker.list_jobs()) == 0

        # 5. Start and stop worker loop cleanly
        await worker.start()
        assert worker._running
        await asyncio.sleep(0.05)
        await worker.stop()
        assert not worker._running
