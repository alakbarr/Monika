"""Regression tests for approval gates in the chat Safety Fortress."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.agent.chat.action_execution import ActionExecutionMixin
from monika.application.agent.chat.action_state import ActionStateMixin
from monika.application.agent.chat.pending_actions import PendingAction
from monika.application.agent.chat.streaming import StreamingMixin, is_mutating_mcp_tool


class _Probe(StreamingMixin):
    def __init__(self, pending_available: bool = True):
        self.tool_event_listener = None
        self.pending_calls: list[dict] = []
        self._last_intercepted_pending = None
        self._pending_available = pending_available

    def _create_pending_action(self, proposed: dict) -> object | None:
        self.pending_calls.append(proposed)
        if not self._pending_available:
            return None
        return SimpleNamespace(action_id="test-pending")


class _Executor:
    def __init__(self):
        self.executed: list[str] = []

    async def execute(self, name: str, args: dict) -> dict:
        self.executed.append(name)
        return {"ok": True}


class _StateProbe(ActionStateMixin):
    def __init__(self):
        self._proposals_paused = False
        self.user_id = 1
        self.is_admin = True
        self.guardrail_controller = MagicMock()
        self.guardrail_controller.validate_tool_call.return_value = SimpleNamespace(allowed=True)


class _ExecutionProbe(ActionExecutionMixin):
    def __init__(self):
        self.settings = {}
        self.is_admin = True
        self.execution_service = MagicMock()


def test_mcp_classifier_defaults_unknown_tools_to_approval():
    assert is_mutating_mcp_tool("mcp_workspace_write_file") is True
    assert is_mutating_mcp_tool("mcp_workspace_read_file") is False
    assert is_mutating_mcp_tool("mcp_workspace_list_files") is False
    assert is_mutating_mcp_tool("mcp_custom_unknown_tool") is True


def test_mcp_write_is_an_allowed_pending_action_type():
    probe = _StateProbe()

    pending = probe._create_pending_action(
        {
            "action_type": "mcp_write",
            "params": {"tool_name": "mcp_workspace_write_file", "args": {"path": "notes.txt"}},
        }
    )

    assert pending is not None
    assert pending.action_type == "mcp_write"
    assert pending.params["tool_name"] == "mcp_workspace_write_file"
    assert "MCP Write Tool" in pending.description


def test_mcp_write_proposal_requires_admin():
    probe = _StateProbe()
    probe.is_admin = False

    pending = probe._create_pending_action(
        {
            "action_type": "mcp_write",
            "params": {"tool_name": "mcp_workspace_write_file", "args": {"path": "notes.txt"}},
        }
    )

    assert pending is None


@pytest.mark.asyncio
async def test_approved_mcp_write_dispatches_to_executor():
    probe = _ExecutionProbe()
    action = PendingAction(
        action_id="mcp_1",
        action_type="mcp_write",
        params={"tool_name": "mcp_workspace_write_file", "args": {"path": "notes.txt"}},
        description="MCP write",
    )
    executor = MagicMock()
    executor.execute = AsyncMock(return_value={"status": "ok"})
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("monika.application.agent.chat.action_execution.get_session", return_value=mock_ctx),
        patch("monika.application.analysis.tools.tool_executor.ToolExecutor", return_value=executor),
    ):
        result = await probe._execute_action(action)

    assert "[MCP WRITE OUTPUT]" in result
    executor.execute.assert_awaited_once_with("mcp_workspace_write_file", {"path": "notes.txt"})


@pytest.mark.asyncio
async def test_mcp_write_requires_operator_approval():
    probe = _Probe()
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("mcp_workspace_write_file", {"path": "notes.txt", "content": "x"})

    assert result["status"] == "pending_operator_approval"
    assert probe.pending_calls
    assert probe.pending_calls[0]["action_type"] == "mcp_write"
    assert executor.executed == []


@pytest.mark.asyncio
async def test_mcp_read_is_not_intercepted():
    probe = _Probe()
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("mcp_workspace_read_file", {"path": "notes.txt"})

    assert result == {"ok": True}
    assert probe.pending_calls == []
    assert executor.executed == ["mcp_workspace_read_file"]


@pytest.mark.asyncio
async def test_mcp_write_blocks_when_approval_unavailable():
    probe = _Probe(pending_available=False)
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("mcp_workspace_write_file", {"path": "notes.txt", "content": "x"})

    assert executor.executed == []
    assert result["status"] == "blocked_by_safety_fortress"


@pytest.mark.asyncio
async def test_mutating_trade_blocks_when_approval_unavailable():
    probe = _Probe(pending_available=False)
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("place_order", {"symbol": "EURUSD", "direction": "buy"})

    assert executor.executed == []
    assert result["status"] == "blocked_by_safety_fortress"


@pytest.mark.asyncio
async def test_terminal_mutation_blocks_when_approval_unavailable():
    probe = _Probe(pending_available=False)
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("terminal", {"command": "rm -rf build"})

    assert executor.executed == []
    assert result["status"] == "blocked_by_safety_fortress"
