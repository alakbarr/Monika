# ==============================================================================
# File: tests/scheduler/test_phase8_universal_cron.py
# ==============================================================================

import os
import time
import pytest
from pathlib import Path

from scheduler.universal_cron_scheduler import UniversalCronScheduler, CronJob
from analysis.tools.domain.cron_tool import handle_manage_cron, CronActionInput
from analysis.tools.unified_registry import unified_tool_registry


def test_universal_cron_anti_suicide_protection(tmp_path):
    db_file = str(tmp_path / "cron_test.db")
    scheduler = UniversalCronScheduler(db_path=db_file)

    # 1. Reject destructive shell command
    with pytest.raises(ValueError, match="prohibited destructive pattern"):
        scheduler.register_job(
            job_id="malicious_1",
            schedule_expression="every 1h",
            prompt="rm -rf / trading-agent system wipe",
        )

    # 2. Reject fork bomb or process killer
    with pytest.raises(ValueError, match="prohibited destructive pattern"):
        scheduler.register_job(
            job_id="malicious_2",
            schedule_expression="every 1h",
            prompt="kill -9 12345",
        )


def test_universal_cron_schedule_and_at_most_once(tmp_path):
    db_file = str(tmp_path / "cron_test.db")
    scheduler = UniversalCronScheduler(db_path=db_file)

    # Register valid job
    job = scheduler.register_job(
        job_id="daily_macro",
        schedule_expression="every 2h",
        prompt="Synthesize Fed interest rate outlook.",
    )
    assert job.job_id == "daily_macro"
    assert job.next_run_at > time.time()

    executed_jobs = []
    scheduler.register_execution_callback(lambda j: executed_jobs.append(j.job_id))

    # Force job to be due
    scheduler.register_job(
        job_id="due_job",
        schedule_expression="every 5m",
        prompt="Poll economic calendar.",
    )
    # Manually set next_run_at to past
    import sqlite3
    conn = sqlite3.connect(db_file)
    conn.execute("UPDATE cron_jobs SET next_run_at = ? WHERE job_id = 'due_job'", (time.time() - 10,))
    conn.commit()
    conn.close()

    # Trigger evaluation
    scheduler._evaluate_due_jobs()

    assert "due_job" in executed_jobs

    # Verify at-most-once: next_run_at has advanced into the future in DB
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT next_run_at FROM cron_jobs WHERE job_id = 'due_job'")
    row = cur.fetchone()
    conn.close()
    assert row[0] > time.time()


def test_universal_cron_inactivity_watchdog(tmp_path):
    db_file = str(tmp_path / "cron_test.db")
    scheduler = UniversalCronScheduler(db_path=db_file)

    # Simulate a job that started 700 seconds ago
    scheduler._running_jobs["hung_job_1"] = time.time() - 700.0

    hung = scheduler.check_hung_jobs(max_runtime_sec=600.0)
    assert "hung_job_1" in hung
    assert "hung_job_1" not in scheduler._running_jobs


@pytest.mark.asyncio
async def test_schedule_cron_job_tool_aliases():
    # Verify tool is registered under both names in unified_tool_registry
    tool1 = unified_tool_registry.get_tool("manage_cron")
    tool2 = unified_tool_registry.get_tool("schedule_cron_job")
    assert tool1 is not None
    assert tool2 is not None
    assert tool1.handler == tool2.handler

    # Test add via tool
    res = await handle_manage_cron(
        CronActionInput(
            action="add",
            name="test_orderbook_scan",
            cron_expression="*/15 * * * *",
            instruction="Scan EURUSD order book depth",
            description="15-min microstructure audit",
        )
    )
    assert res["success"] is True

    # Test list via tool
    list_res = await handle_manage_cron(CronActionInput(action="list"))
    assert list_res["success"] is True
    job_names = [j["name"] for j in list_res["jobs"]]
    assert "test_orderbook_scan" in job_names

    # Clean up
    await handle_manage_cron(CronActionInput(action="remove", name="test_orderbook_scan"))


@pytest.mark.asyncio
async def test_cli_and_bot_cron_command_routing():
    from unittest.mock import MagicMock
    from cli.chat.commands import ChatCommandRouter
    from cli.chat.renderer import ChatRenderer
    from cli.chat.prompt import ChatPromptManager

    renderer = MagicMock()
    prompt_mgr = MagicMock(spec=ChatPromptManager)
    router = ChatCommandRouter(renderer=renderer, prompt_manager=prompt_mgr)

    # Test /cron list handling
    res = await router.handle("/cron list")
    assert res.handled is True

    # Test /cron add handling
    res_add = await router.handle("/cron add test_auto_job */10 * * * * Scan liquidity sweeps")
    assert res_add.handled is True

    # Test /cron remove handling
    res_rm = await router.handle("/cron remove test_auto_job")
    assert res_rm.handled is True

