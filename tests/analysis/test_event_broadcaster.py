import asyncio
import warnings
import pytest
from monika.application.analysis.event_broadcaster import (
    register_event_listener,
    unregister_event_listener,
    emit_analysis_event,
    _dispatch_to_listener,
)


def test_event_broadcaster_sync_listener():
    received = []

    def sync_listener(event_type, payload):
        received.append((event_type, payload))

    register_event_listener(sync_listener)
    try:
        emit_analysis_event("test_sync_event", {"key": "value"})
        assert len(received) == 1
        assert received[0][0] == "test_sync_event"
        assert received[0][1]["key"] == "value"
    finally:
        unregister_event_listener(sync_listener)


def test_event_broadcaster_coroutine_function_without_loop_no_warning():
    received = []

    async def async_listener(event_type, payload):
        received.append((event_type, payload))

    # In a synchronous context with no running loop, calling _dispatch_to_listener
    # must NOT raise or emit RuntimeWarning: coroutine was never awaited.
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always", RuntimeWarning)
        _dispatch_to_listener(async_listener, "test_async_event", {"key": "val"})

    coroutine_warnings = [
        w for w in recorded_warnings if issubclass(w.category, RuntimeWarning) and "coroutine" in str(w.message)
    ]
    assert len(coroutine_warnings) == 0, f"Unexpected coroutine warnings: {coroutine_warnings}"


@pytest.mark.asyncio
async def test_event_broadcaster_coroutine_function_with_loop():
    received = []

    async def async_listener(event_type, payload):
        received.append((event_type, payload))

    register_event_listener(async_listener)
    try:
        emit_analysis_event("test_async_event", {"key": "val"})
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0][0] == "test_async_event"
        assert received[0][1]["key"] == "val"
    finally:
        unregister_event_listener(async_listener)


def test_event_broadcaster_listener_raising_exception_safe():
    def broken_listener(event_type, payload):
        raise ValueError("Simulated error in listener")

    register_event_listener(broken_listener)
    try:
        # Should not raise exception
        emit_analysis_event("test_fail_event", {})
    finally:
        unregister_event_listener(broken_listener)
