"""Regression tests for local file-write approval gates in the chat Safety Fortress."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.agent.chat.action_execution import ActionExecutionMixin
from monika.application.agent.chat.action_state import ActionStateMixin
from monika.application.agent.chat.pending_actions import PendingAction
from monika.application.agent.chat.streaming import StreamingMixin


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
        return SimpleNamespace(action_id="test-file-pending")


class _Executor:
    def __init__(self):
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, name: str, args: dict) -> dict:
        self.executed.append((name, args))
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


@pytest.mark.asyncio
async def test_file_write_requires_operator_approval():
    probe = _Probe()
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("write_file", {"path": "src/x.py", "content": "x"})

    assert result["status"] == "pending_operator_approval"
    assert result["action_type"] == "file_write"
    assert probe.pending_calls[0]["action_type"] == "file_write"
    assert executor.executed == []


@pytest.mark.asyncio
async def test_file_patch_requires_operator_approval():
    probe = _Probe()
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute(
        "patch",
        {"path": "src/x.py", "old_string": "a", "new_string": "b"},
    )

    assert result["status"] == "pending_operator_approval"
    assert probe.pending_calls[0]["params"]["tool_name"] == "patch"
    assert executor.executed == []


@pytest.mark.asyncio
async def test_file_read_is_not_intercepted():
    probe = _Probe()
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("read_file", {"path": "src/x.py"})

    assert result == {"ok": True}
    assert probe.pending_calls == []
    assert executor.executed == [("read_file", {"path": "src/x.py"})]


@pytest.mark.asyncio
async def test_file_write_blocks_when_approval_unavailable():
    probe = _Probe(pending_available=False)
    executor = _Executor()
    probe._instrument_executor(executor)

    result = await executor.execute("write_file", {"path": "src/x.py", "content": "x"})

    assert result["status"] == "blocked_by_safety_fortress"
    assert executor.executed == []


def test_file_write_proposal_requires_admin_and_describes_path():
    probe = _StateProbe()

    pending = probe._create_pending_action(
        {
            "action_type": "file_write",
            "params": {"tool_name": "write_file", "args": {"path": "src/x.py", "content": "x"}},
        }
    )

    assert pending is not None
    assert pending.action_type == "file_write"
    assert "File Write Tool" in pending.description
    assert "src/x.py" in pending.description

    probe.is_admin = False
    assert (
        probe._create_pending_action(
            {
                "action_type": "file_write",
                "params": {"tool_name": "write_file", "args": {"path": "src/x.py"}},
            }
        )
        is None
    )


@pytest.mark.asyncio
async def test_approved_file_write_dispatches_to_executor():
    probe = _ExecutionProbe()
    action = PendingAction(
        action_id="file_1",
        action_type="file_write",
        params={"tool_name": "patch", "args": {"path": "src/x.py", "old_string": "a", "new_string": "b"}},
        description="File write",
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

    assert "[FILE WRITE OUTPUT]" in result
    executor.execute.assert_awaited_once_with("patch", {"path": "src/x.py", "old_string": "a", "new_string": "b"})
