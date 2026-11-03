# ==============================================================================
# File: tests/test_memory_supervisor.py
# Description: Unit tests for 24/7 MemorySupervisor and progressive compaction.
# ==============================================================================

import asyncio
import pytest
from monika.application.agent.monitors.memory_supervisor import (
    MemorySupervisor,
    run_memory_supervisor,
)


def test_memory_supervisor_get_rss():
    supervisor = MemorySupervisor()
    rss = supervisor.get_rss_mb()
    assert isinstance(rss, float)
    assert rss > 0.0


def test_memory_supervisor_compaction():
    supervisor = MemorySupervisor()
    result = supervisor.compact_memory(reason="test")
    assert isinstance(result, dict)
    assert "rss_before_mb" in result
    assert "rss_after_mb" in result
    assert "freed_mb" in result
    assert "gc_collected" in result
    assert "pruned_tasks" in result
    assert "os_trimmed" in result
    assert result["rss_before_mb"] > 0.0
    assert result["rss_after_mb"] > 0.0


@pytest.mark.asyncio
async def test_memory_supervisor_lifecycle():
    supervisor = MemorySupervisor(interval_seconds=0.05, compact_mb=10.0)
    task = supervisor.start()
    assert task is not None
    assert not task.done()

    # Let loop run for a short duration
    await asyncio.sleep(0.12)

    supervisor.stop()
    await asyncio.sleep(0.02)
    assert task.done()
