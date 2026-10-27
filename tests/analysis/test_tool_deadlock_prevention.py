import asyncio
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from monika.application.analysis.tools.executor import ToolExecutor
from monika.infrastructure.llm.caveman_compressor import compress_tool_payload


@pytest.mark.asyncio
async def test_economic_calendar_reentrancy_deadlock_prevention():
    """Verify get_economic_calendar does not deadlock when executed under an active _session_lock."""
    mock_session = AsyncMock()
    mock_session._session_lock = asyncio.Lock()
    mock_session.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_result

    executor = ToolExecutor(mock_session, symbol="EURUSD")

    async with asyncio.timeout(2.0):
        res = await executor.execute(
            "get_economic_calendar",
            {"impact_filter": "high_and_medium", "hours_ahead": 48, "hours_behind": 12},
        )

    assert isinstance(res, dict)
    assert res.get("count") == 0
    assert res.get("events") == []


@pytest.mark.asyncio
async def test_composite_tools_deadlock_prevention():
    """Verify that composite tools execute sequentially without circular asyncio.gather deadlocks."""
    mock_session = AsyncMock()
    mock_session._session_lock = asyncio.Lock()
    mock_session.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_result

    executor = ToolExecutor(mock_session, symbol="EURUSD")

    # Mock low-level executor calls so composite tools return promptly
    orig_execute = executor.execute

    async def mock_execute(tool_name, tool_input):
        if tool_name in ("get_price_data", "get_technical_analysis", "get_institutional_data", "get_market_context"):
            return await orig_execute(tool_name, tool_input)
        return {"status": "ok", "mocked_tool": tool_name}

    executor.execute = mock_execute

    for comp_tool in ("get_price_data", "get_technical_analysis", "get_institutional_data", "get_market_context"):
        async with asyncio.timeout(2.0):
            res = await executor.execute(comp_tool, {"symbol": "EURUSD"})
        assert isinstance(res, dict)
        assert "error" not in res or not res["error"]


def test_caveman_compressor_numpy_array_safe():
    """Verify that caveman_compressor safely compresses payloads containing NumPy arrays without ValueError."""
    payload = {
        "regular_list": [1, 2, 3],
        "empty_list": [],
        "np_array": np.array([1.0, 2.0, 3.0]),
        "np_empty": np.array([]),
        "nested": {
            "matrix": np.zeros((2, 2)),
            "val": 42.1234567,
        },
    }

    # Must not raise: ValueError: The truth value of an empty array is ambiguous
    compressed = compress_tool_payload(payload, strip_empty_collections=True)

    assert "regular_list" in compressed
    assert "empty_list" not in compressed  # Stripped
    assert "np_array" in compressed
    assert compressed["nested"]["val"] == 42.12346


def test_stage2_prefetcher_fetch_errors_formatting():
    """Verify that Stage2DataBundler._format_fetch_error format string never outputs blank error names."""
    # TimeoutError has empty str() in Python
    err_timeout = TimeoutError()
    assert str(err_timeout) == ""

    formatted_timeout = Stage2DataBundler._format_fetch_error("get_economic_calendar", err_timeout)
    assert formatted_timeout == "get_economic_calendar: TimeoutError"

    # Regular error with text message
    err_custom = ValueError("Connection refused by peer")
    formatted_custom = Stage2DataBundler._format_fetch_error("get_price_history", err_custom)
    assert formatted_custom == "get_price_history: Connection refused by peer"
