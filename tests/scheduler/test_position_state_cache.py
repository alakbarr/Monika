"""
Unit tests for ActivePositionStateCache and zero-DB tick path optimizations.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.application.scheduler.position_guardian import PositionGuardian
from monika.application.scheduler.position_state_cache import (
    ActivePositionStateCache,
    get_position_state_cache,
    reset_position_state_cache,
)
from monika.application.scheduler.trailing_stop_manager import TrailingStopManager
from monika.core.primitives.event_bus import TickPriceEvent


@pytest.fixture(autouse=True)
def cleanup_cache():
    reset_position_state_cache()
    yield
    reset_position_state_cache()


def test_cache_basic_normalization_and_tracking():
    cache = ActivePositionStateCache(ttl_seconds=10.0)
    assert not cache.is_fresh()
    assert not cache.has_any_open_positions

    cache.update_snapshot(open_symbols={"EUR/USD", "XAUUSD"}, orphan_symbols={"GBPUSD"})
    assert cache.is_fresh()
    assert cache.has_any_open_positions
    assert cache.has_open_position("EURUSD")
    assert cache.has_open_position("eur/usd")
    assert cache.has_open_position("XAUUSD")
    assert not cache.has_open_position("GBPUSD")
    assert cache.has_orphan_position("GBPUSD")
    assert cache.has_active_or_orphan_position("GBPUSD")
    assert cache.has_active_or_orphan_position("EURUSD")
    assert not cache.has_active_or_orphan_position("BTCUSD")

    cache.mark_symbol_closed("EURUSD")
    assert not cache.has_open_position("EURUSD")

    cache.mark_symbol_open("BTCUSD")
    assert cache.has_open_position("btcusd")

    cache.invalidate()
    assert not cache.is_fresh()


@pytest.mark.asyncio
async def test_cache_ensure_fresh_with_session_factory():
    cache = ActivePositionStateCache(ttl_seconds=5.0)

    class FakeConfig:
        value = "true"

    class FakePosRow:
        def __init__(self, sym: str, stat: str):
            self.symbol = sym
            self.status = stat

    class FakeResult:
        def __init__(self, rows=None, scalar_val=None):
            self._rows = rows or []
            self._scalar = scalar_val

        def scalar_one_or_none(self):
            return self._scalar

        def all(self):
            return self._rows

    queries_count = 0

    class FakeSession:
        async def execute(self, stmt):
            nonlocal queries_count
            queries_count += 1
            sql = str(stmt).lower()
            if "system_config" in sql:
                return FakeResult(scalar_val=FakeConfig())
            return FakeResult(rows=[FakePosRow("EURUSD", "open"), FakePosRow("GBPUSD", "orphan_pending_close")])

    @asynccontextmanager
    async def fake_factory():
        yield FakeSession()

    await cache.ensure_fresh(session_factory=fake_factory)
    assert cache.is_fresh()
    assert queries_count == 2
    assert cache.kill_switch_active
    assert cache.has_open_position("EURUSD")
    assert cache.has_orphan_position("GBPUSD")

    # Second call within TTL should return immediately without opening session
    await cache.ensure_fresh(session_factory=fake_factory)
    assert queries_count == 2


@pytest.mark.asyncio
async def test_trailing_stop_manager_zero_db_sessions_when_flat():
    cache = ActivePositionStateCache(ttl_seconds=10.0)
    cache.update_snapshot(open_symbols=set())  # Flat: 0 open positions

    settings = {"trading": {"trailing_stop": {"enabled": True}}}
    mgr = TrailingStopManager(settings=settings, execution_service=None, state_cache=cache)

    session_opened = False

    @asynccontextmanager
    async def failing_session():
        nonlocal session_opened
        session_opened = True
        yield MagicMock()

    # Even with un-throttled ticks, zero DB sessions must be opened
    for _ in range(5):
        if hasattr(mgr, "_last_tick_check"):
            mgr._last_tick_check.clear()
        tick = TickPriceEvent(symbol="EURUSD", bid=1.1000, ask=1.1002, last=1.1001)
        await mgr.on_tick(tick)

    assert not session_opened


@pytest.mark.asyncio
async def test_position_guardian_zero_db_sessions_when_flat():
    cache = ActivePositionStateCache(ttl_seconds=10.0)
    cache.update_snapshot(open_symbols=set(), orphan_symbols=set(), kill_switch_active=False)

    settings = {"trading": {"position_guardian": {"enabled": True}}}
    guardian = PositionGuardian(settings=settings, execution_service=None, state_cache=cache)

    session_opened = False

    @asynccontextmanager
    async def failing_session():
        nonlocal session_opened
        session_opened = True
        yield MagicMock()

    for _ in range(5):
        if hasattr(guardian, "_last_tick_check"):
            guardian._last_tick_check.clear()
        tick = TickPriceEvent(symbol="EURUSD", bid=1.1000, ask=1.1002, last=1.1001)
        await guardian.on_tick(tick)

    assert not session_opened


@pytest.mark.asyncio
async def test_position_guardian_immediate_kill_on_cached_flag():
    cache = ActivePositionStateCache(ttl_seconds=10.0)
    cache.update_snapshot(open_symbols=set(), orphan_symbols=set(), kill_switch_active=True)

    mock_exec = AsyncMock()
    settings = {"trading": {"position_guardian": {"enabled": True}}}
    guardian = PositionGuardian(settings=settings, execution_service=mock_exec, state_cache=cache)

    tick = TickPriceEvent(symbol="EURUSD", bid=1.1000, ask=1.1002, last=1.1001)
    await guardian.on_tick(tick)

    mock_exec.kill_switch.assert_awaited_once()
