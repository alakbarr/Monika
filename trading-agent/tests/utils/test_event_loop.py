"""Unit tests for utils.infra.event_loop module."""

import asyncio
import sys
import pytest
from utils.infra.event_loop import get_loop_factory, run_async


def test_get_loop_factory():
    """Verify get_loop_factory returns SelectorEventLoop on Windows and empty dict elsewhere."""
    factory_kwargs = get_loop_factory()
    if sys.platform == "win32":
        assert "loop_factory" in factory_kwargs
        assert factory_kwargs["loop_factory"] is asyncio.SelectorEventLoop
    else:
        assert factory_kwargs == {}


def test_run_async_executes_coroutine_with_correct_loop():
    """Verify run_async executes a coroutine and sets SelectorEventLoop on Windows."""
    async def sample_coro():
        current_loop = asyncio.get_running_loop()
        return type(current_loop).__name__

    loop_name = run_async(sample_coro())
    if sys.platform == "win32":
        assert "Selector" in loop_name or "selector" in loop_name.lower()
    assert isinstance(loop_name, str)
