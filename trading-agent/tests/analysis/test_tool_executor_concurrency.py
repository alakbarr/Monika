import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from analysis.tools.executor import ToolExecutor
from analysis.providers.base_provider import BaseLLMClient
from analysis.providers.anthropic_provider import AnthropicProvider


@pytest.mark.asyncio
async def test_tool_executor_shares_session_lock():
    """Verify that multiple ToolExecutor instances bound to the same session share the same asyncio.Lock."""
    mock_session = MagicMock(spec=AsyncSession)
    
    ex1 = ToolExecutor(session=mock_session, settings={})
    assert hasattr(mock_session, "_session_lock")
    assert ex1._session_lock is mock_session._session_lock

    ex2 = ToolExecutor(session=mock_session, settings={})
    assert ex2._session_lock is mock_session._session_lock
    assert ex1._session_lock is ex2._session_lock


@pytest.mark.asyncio
async def test_concurrent_tool_execution_serialized_by_session_lock():
    """Verify that concurrent tool executions on the same session are serialized by session_lock."""
    mock_session = MagicMock(spec=AsyncSession)
    mock_session._session_lock = asyncio.Lock()
    
    executor = ToolExecutor(session=mock_session, settings={})
    execution_order = []
    
    async def slow_handler_1(inp):
        execution_order.append("start_1")
        await asyncio.sleep(0.05)
        execution_order.append("end_1")
        return {"status": "ok1"}

    async def slow_handler_2(inp):
        execution_order.append("start_2")
        await asyncio.sleep(0.01)
        execution_order.append("end_2")
        return {"status": "ok2"}

    executor._tool_tool1 = slow_handler_1
    executor._tool_tool2 = slow_handler_2
    
    res1, res2 = await asyncio.gather(
        executor.execute("tool1", {}),
        executor.execute("tool2", {})
    )
    
    assert res1.get("status") == "ok1"
    assert res2.get("status") == "ok2"
    
    # Since both acquired the shared session_lock, tool1 should fully finish before tool2 starts
    assert execution_order == ["start_1", "end_1", "start_2", "end_2"]


@pytest.mark.asyncio
async def test_transient_concurrency_error_retry_and_rollback():
    """Verify that InterfaceError ('another operation is in progress') triggers rollback and retries."""
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.rollback = AsyncMock()
    
    executor = ToolExecutor(session=mock_session, settings={})
    call_count = 0

    async def flaky_handler(inp):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("cannot perform operation: another operation is in progress")
        return {"status": "recovered"}

    executor._tool_flaky = flaky_handler
    
    res = await executor.execute("flaky", {})
    assert res.get("status") == "recovered"
    assert call_count == 2
    assert mock_session.rollback.await_count >= 1


@pytest.mark.asyncio
async def test_base_provider_log_tool_call_uses_isolated_session():
    """Verify BaseLLMClient._log_tool_call does not call commit on the caller's session."""
    caller_session = MagicMock(spec=AsyncSession)
    caller_session.commit = AsyncMock()
    caller_session.add = MagicMock()

    isolated_session = MagicMock(spec=AsyncSession)
    isolated_session.commit = AsyncMock()
    isolated_session.add = MagicMock()

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return isolated_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    with patch("database.db.get_session", return_value=AsyncContextManagerMock()):
        with patch.object(BaseLLMClient, "__abstractmethods__", set()):
            provider = BaseLLMClient(model="test_model", settings={})
            await provider._log_tool_call(caller_session, "fundamental", "get_dxy", {}, {"result": 1})

    # Caller session should NOT be touched or committed
    caller_session.commit.assert_not_called()
    caller_session.add.assert_not_called()

    # Isolated session should have added and committed the log entry
    isolated_session.add.assert_called_once()
    isolated_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_anthropic_provider_log_tool_call_uses_isolated_session():
    """Verify AnthropicProvider._log_tool_call uses isolated session."""
    caller_session = MagicMock(spec=AsyncSession)
    caller_session.commit = AsyncMock()
    caller_session.add = MagicMock()

    isolated_session = MagicMock(spec=AsyncSession)
    isolated_session.commit = AsyncMock()
    isolated_session.add = MagicMock()

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return isolated_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    with patch("database.db.get_session", return_value=AsyncContextManagerMock()):
        with patch.object(AnthropicProvider, "__init__", lambda self, *args, **kwargs: None):
            provider = AnthropicProvider()
            await provider._log_tool_call(caller_session, "fundamental", "get_treasury_yields", {}, {"status": "ok"})

    caller_session.commit.assert_not_called()
    caller_session.add.assert_not_called()
    isolated_session.add.assert_called_once()
    isolated_session.commit.assert_awaited_once()
