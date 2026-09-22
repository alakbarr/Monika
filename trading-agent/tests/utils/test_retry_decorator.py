"""
Unit tests for the retry_decorator utility.
"""

import asyncio
import pytest
from unittest.mock import MagicMock
from utils.retry_decorator import retryable, _calculate_delay


def test_calculate_delay_exponential_and_max():
    # Attempt 0: 1.0 * (2^0) = 1.0
    delay_0 = _calculate_delay(attempt=0, base_delay=1.0, max_delay=10.0, backoff_factor=2.0, jitter=False)
    assert delay_0 == 1.0

    # Attempt 1: 1.0 * (2^1) = 2.0
    delay_1 = _calculate_delay(attempt=1, base_delay=1.0, max_delay=10.0, backoff_factor=2.0, jitter=False)
    assert delay_1 == 2.0

    # Attempt 2: 1.0 * (2^2) = 4.0
    delay_2 = _calculate_delay(attempt=2, base_delay=1.0, max_delay=10.0, backoff_factor=2.0, jitter=False)
    assert delay_2 == 4.0

    # Attempt 10: capped at max_delay 10.0
    delay_10 = _calculate_delay(attempt=10, base_delay=1.0, max_delay=10.0, backoff_factor=2.0, jitter=False)
    assert delay_10 == 10.0


def test_calculate_delay_jitter():
    # With jitter, delay should be between 75% and 100% of base calculation
    delay_jitter = _calculate_delay(attempt=1, base_delay=2.0, max_delay=10.0, backoff_factor=2.0, jitter=True)
    assert 3.0 <= delay_jitter <= 4.0


@pytest.mark.asyncio
async def test_async_retryable_success_first_try():
    calls = 0

    @retryable(max_retries=3, base_delay=0.01)
    async def sample_task():
        nonlocal calls
        calls += 1
        return "success"

    result = await sample_task()
    assert result == "success"
    assert calls == 1


@pytest.mark.asyncio
async def test_async_retryable_success_after_retries():
    calls = 0
    callback_mock = MagicMock()

    @retryable(max_retries=3, base_delay=0.01, jitter=False, on_retry_callback=callback_mock)
    async def flaky_task():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("Temporary glitch")
        return "recovered"

    result = await flaky_task()
    assert result == "recovered"
    assert calls == 3
    assert callback_mock.call_count == 2


@pytest.mark.asyncio
async def test_async_retryable_exhaust_retries():
    calls = 0

    @retryable(max_retries=2, base_delay=0.01, jitter=False)
    async def failing_task():
        nonlocal calls
        calls += 1
        raise TimeoutError("Dead end")

    with pytest.raises(TimeoutError, match="Dead end"):
        await failing_task()
    assert calls == 3  # initial + 2 retries


def test_sync_retryable_success_after_retries():
    calls = 0

    @retryable(max_retries=2, base_delay=0.01, jitter=False)
    def sync_flaky():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("Transient error")
        return 42

    result = sync_flaky()
    assert result == 42
    assert calls == 2


def test_sync_retryable_unhandled_exception():
    @retryable(max_retries=2, base_delay=0.01, retryable_exceptions=(ValueError,))
    def strict_task():
        raise KeyError("Not in retryable list")

    with pytest.raises(KeyError):
        strict_task()
