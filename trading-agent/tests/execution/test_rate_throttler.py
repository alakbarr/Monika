# ==============================================================================
# File: tests/execution/test_rate_throttler.py
# ==============================================================================

import asyncio
import pytest
import time
from execution.rate_throttler import RateThrottler, ThrottleVerdict


@pytest.mark.asyncio
async def test_rate_throttler_basic_allow():
    throttler = RateThrottler(max_per_second=2, max_per_minute=15)
    v1 = await throttler.acquire()
    assert v1.allowed is True
    assert v1.retry_after == 0.0

    v2 = await throttler.acquire()
    assert v2.allowed is True
    assert v2.retry_after == 0.0


@pytest.mark.asyncio
async def test_rate_throttler_second_limit_burst():
    throttler = RateThrottler(max_per_second=2, max_per_minute=15)
    now = 1000.0
    v1 = await throttler.acquire(now=now)
    assert v1.allowed is True

    v2 = await throttler.acquire(now=now + 0.1)
    assert v2.allowed is True

    # Third order in same 1s window must be blocked
    v3 = await throttler.acquire(now=now + 0.2)
    assert v3.allowed is False
    assert v3.retry_after > 0
    assert "Second rate limit exceeded" in v3.reason


@pytest.mark.asyncio
async def test_rate_throttler_minute_limit():
    throttler = RateThrottler(max_per_second=100, max_per_minute=5)
    now = 1000.0
    for i in range(5):
        v = await throttler.acquire(now=now + i * 2.0)
        assert v.allowed is True

    # 6th order in same 60s window must be blocked by minute limit
    v6 = await throttler.acquire(now=now + 15.0)
    assert v6.allowed is False
    assert v6.retry_after > 0
    assert "Minute rate limit exceeded" in v6.reason


@pytest.mark.asyncio
async def test_rate_throttler_second_window_refill():
    throttler = RateThrottler(max_per_second=2, max_per_minute=15)
    now = 1000.0
    await throttler.acquire(now=now)
    await throttler.acquire(now=now + 0.2)

    # Denied at now + 0.5
    v_denied = await throttler.acquire(now=now + 0.5)
    assert v_denied.allowed is False

    # Allowed at now + 1.1 (after first order expired from 1s window)
    v_refilled = await throttler.acquire(now=now + 1.1)
    assert v_refilled.allowed is True


@pytest.mark.asyncio
async def test_rate_throttler_wait_and_acquire():
    throttler = RateThrottler(max_per_second=1, max_per_minute=15)
    v1 = await throttler.acquire()
    assert v1.allowed is True

    # wait_and_acquire should wait until the 1s window clears
    t0 = time.monotonic()
    v2 = await throttler.wait_and_acquire(timeout=2.0)
    elapsed = time.monotonic() - t0
    assert v2.allowed is True
    assert elapsed >= 0.9


@pytest.mark.asyncio
async def test_rate_throttler_wait_and_acquire_zero_timeout():
    throttler = RateThrottler(max_per_second=1, max_per_minute=15)
    # Available slot should acquire immediately even with timeout=0
    v1 = await throttler.wait_and_acquire(timeout=0.0)
    assert v1.allowed is True

    # When exhausted, timeout=0 should return blocked immediately without sleeping
    v2 = await throttler.wait_and_acquire(timeout=0.0)
    assert v2.allowed is False
    assert v2.retry_after > 0


@pytest.mark.asyncio
async def test_rate_throttler_concurrency():
    throttler = RateThrottler(max_per_second=5, max_per_minute=10)

    results = await asyncio.gather(*[throttler.acquire() for _ in range(8)])
    allowed_count = sum(1 for r in results if r.allowed)
    blocked_count = sum(1 for r in results if not r.allowed)

    assert allowed_count == 5
    assert blocked_count == 3


@pytest.mark.asyncio
async def test_rate_throttler_reset():
    throttler = RateThrottler(max_per_second=1, max_per_minute=1)
    v1 = await throttler.acquire()
    assert v1.allowed is True

    v2 = await throttler.acquire()
    assert v2.allowed is False

    await throttler.reset()
    v3 = await throttler.acquire()
    assert v3.allowed is True


@pytest.mark.asyncio
async def test_rate_throttler_invalid_zero_limit_clamping():
    # If 0 is passed, it should safely clamp to at least 1 and not raise IndexError
    throttler = RateThrottler(max_per_second=0, max_per_minute=0)
    assert throttler.max_per_second == 1
    assert throttler.max_per_minute == 1

    v1 = await throttler.acquire()
    assert v1.allowed is True

    v2 = await throttler.acquire()
    assert v2.allowed is False
    assert v2.retry_after > 0


@pytest.mark.asyncio
async def test_position_synchronizer_throttling():
    from unittest.mock import AsyncMock, MagicMock, patch
    from execution.service.position_synchronizer import PositionSynchronizerMixin

    class DummySyncService(PositionSynchronizerMixin):
        def __init__(self, throttler):
            self.settings = {}
            self.mt5 = MagicMock()
            self.mt5.modify_position = AsyncMock(return_value={"success": True})
            self.rate_throttler = throttler

    with patch("execution.service.position_synchronizer.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        throttler = RateThrottler(max_per_second=1, max_per_minute=10)
        svc = DummySyncService(throttler)

        # First modification passes
        res1 = await svc.modify_position_sl_tp(ticket=101, sl=2000.0)
        assert res1.get("success") is True

        # Second immediate modification gets throttled
        res2 = await svc.modify_position_sl_tp(ticket=102, sl=2005.0)
        assert res2.get("success") is False
        assert res2.get("retcode") == 10027
        assert "throttled" in res2.get("error", "").lower()
