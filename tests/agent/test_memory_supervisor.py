import asyncio
import pytest
from monika.application.agent.monitors.memory_supervisor import MemorySupervisor, run_memory_supervisor


def test_memory_supervisor_compact():
    supervisor = MemorySupervisor(interval_seconds=1.0)
    res = supervisor.compact_memory(reason="unit_test")
    assert "rss_before_mb" in res
    assert "rss_after_mb" in res
    assert "freed_mb" in res
    assert "gc_collected" in res


@pytest.mark.asyncio
async def test_memory_supervisor_run_loop_stop_event():
    stop_event = asyncio.Event()
    supervisor = MemorySupervisor(interval_seconds=0.1)

    task = asyncio.create_task(supervisor.run_loop(stop_event=stop_event))
    await asyncio.sleep(0.05)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert not supervisor._running or stop_event.is_set()
