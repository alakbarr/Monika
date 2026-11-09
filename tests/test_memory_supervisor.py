# ==============================================================================
# File: tests/test_memory_supervisor.py
# Description: Unit tests for 24/7 MemorySupervisor and progressive compaction.
# ==============================================================================

import asyncio
import pytest
from monika.application.agent.monitors.memory_supervisor import (
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_HARD_LIMIT_MB,
    DEFAULT_WARN_MB,
    DEFAULT_COMPACT_MB,
    MemorySupervisor,
    run_memory_supervisor,
)
from monika.core.primitives.compaction import CompactionTarget, get_compaction_registry
from monika.application.agent.readonly_replay_cache import ReadOnlyReplayCache


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
    assert result["tier"] == 1
    assert result["rss_before_mb"] > 0.0
    assert result["rss_after_mb"] > 0.0


def test_memory_supervisor_compaction_tiers():
    supervisor = MemorySupervisor()
    r1 = supervisor.compact_memory(reason="tier1_test", tier=1)
    r2 = supervisor.compact_memory(reason="tier2_test", tier=2)
    r3 = supervisor.compact_memory(reason="tier3_test", tier=3)
    assert r1["tier"] == 1
    assert r2["tier"] == 2
    assert r3["tier"] == 3


def test_memory_supervisor_compaction_registry_integration():
    registry = get_compaction_registry()

    class MockTarget(CompactionTarget):
        def __init__(self):
            self.called_tier = 0

        def compact(self, tier: int) -> int:
            self.called_tier = tier
            return 42

    target = MockTarget()
    registry.register(target)
    try:
        supervisor = MemorySupervisor()
        res = supervisor.compact_memory(reason="registry_test", tier=3)
        assert target.called_tier == 3
        assert res["registry_freed"] >= 42
    finally:
        registry.unregister(target)


def test_readonly_replay_cache_compaction_target():
    cache = ReadOnlyReplayCache.get_instance()
    cache.put("test_tool", {"arg": 1}, "res1", ttl_seconds=0.01)
    cache.put("test_tool", {"arg": 2}, "res2", ttl_seconds=300.0)

    import time

    time.sleep(0.02)

    # Tier 1 should reap expired entries
    freed = cache.compact(tier=1)
    assert freed >= 1

    # Tier 3 should fully wipe
    freed3 = cache.compact(tier=3)
    assert freed3 >= 1
    assert len(cache._bounded_cache) == 0


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


@pytest.mark.asyncio
async def test_memory_supervisor_cooldown_throttling():
    supervisor = MemorySupervisor(
        interval_seconds=0.02,
        warn_mb=1.0,
        compact_mb=2.0,
        hard_limit_mb=3.0,
        cooldown_seconds=60.0,
    )
    stop_event = asyncio.Event()

    task = asyncio.create_task(supervisor.run_loop(stop_event=stop_event))
    await asyncio.sleep(0.08)

    # First critical log timestamp should be set
    assert supervisor._last_critical_log_time > 0.0
    first_log_time = supervisor._last_critical_log_time

    # Run for another cycle, timestamp must remain identical due to 60s cooldown
    await asyncio.sleep(0.05)
    assert supervisor._last_critical_log_time == first_log_time

    stop_event.set()
    await asyncio.wait_for(task, timeout=1.0)
