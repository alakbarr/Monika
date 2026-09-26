# ==============================================================================
# File: tests/plugin_kernel/test_phase7_plugin_lifecycle.py
# ==============================================================================

import asyncio
import pytest
from pathlib import Path

from harness.lifecycle import (
    ReplacementCoordinator,
    ReplacementLease,
    ReplacementTimeoutError,
    safe_dispatch_hook,
    get_plugin_storage_dir,
)


class MockPlugin:
    def __init__(self, name: str):
        self.name = name
        self.is_running = True
        self.drained = False

    async def on_stop(self):
        await asyncio.sleep(0.05)
        self.is_running = False
        self.drained = True

    async def on_start(self):
        await asyncio.sleep(0.05)
        self.is_running = True


@pytest.mark.asyncio
async def test_replacement_coordinator_atomic_swap():
    coordinator = ReplacementCoordinator(default_drain_timeout_sec=2.0)
    plugin_id = "test_custom_indicator"

    old_plugin = MockPlugin("v1")
    new_plugin = MockPlugin("v2")

    assert old_plugin.is_running is True
    assert old_plugin.drained is False

    success, msg = await coordinator.replace_component(
        plugin_id=plugin_id,
        old_component=old_plugin,
        new_component=new_plugin,
    )

    assert success is True
    assert "successfully replaced" in msg
    assert old_plugin.is_running is False
    assert old_plugin.drained is True
    assert new_plugin.is_running is True


@pytest.mark.asyncio
async def test_replacement_lease_concurrency_lock():
    coordinator = ReplacementCoordinator()
    plugin_id = "discord_alerts"

    async with coordinator.acquire_lease(plugin_id, timeout_sec=1.0):
        # A second concurrent lease request should timeout
        with pytest.raises(ReplacementTimeoutError):
            async with coordinator.acquire_lease(plugin_id, timeout_sec=0.1):
                pass


@pytest.mark.asyncio
async def test_safe_dispatch_hook_timeout_and_error_handling():
    # 1. Normal hook
    async def normal_hook(x):
        return x * 2

    res_normal = await safe_dispatch_hook(normal_hook, 21, timeout_sec=1.0)
    assert res_normal == 42

    # 2. Hook that raises an exception
    def broken_hook():
        raise ValueError("Critical plugin bug")

    res_broken = await safe_dispatch_hook(broken_hook, timeout_sec=1.0, default="safe_default")
    assert res_broken == "safe_default"

    # 3. Hook that exceeds timeout
    async def slow_hook():
        await asyncio.sleep(0.5)
        return "too_late"

    res_slow = await safe_dispatch_hook(slow_hook, timeout_sec=0.1, default="timeout_fallback")
    assert res_slow == "timeout_fallback"


def test_get_plugin_storage_dir_sanitization(tmp_path):
    # Standard plugin ID
    dir1 = get_plugin_storage_dir("my_plugin_1", base_dir=tmp_path)
    assert dir1.name == "my_plugin_1"
    assert dir1.exists()

    # Traversal attempt
    dir2 = get_plugin_storage_dir("../../../evil_hack", base_dir=tmp_path)
    # The clean_id strips ../ so it becomes evil_hack
    assert ".." not in str(dir2)
    assert dir2.exists()
