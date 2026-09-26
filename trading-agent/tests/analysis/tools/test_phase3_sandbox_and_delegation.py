# ==============================================================================
# File: tests/analysis/tools/test_phase3_sandbox_and_delegation.py
# Description: Unit tests for Tier3 persistent Docker sandbox and Subagent delegation tool
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.tools.environments.tier3_docker import Tier3DockerEnvironment, Tier3DockerContainerEnvironment
from analysis.tools.domain.delegate_tool import handle_delegate_task, DelegateTaskInput, _ACTIVE_SUBAGENTS


@pytest.mark.asyncio
async def test_tier3_docker_persistent_container_logic():
    mock_fallback = MagicMock()
    mock_fallback.run_command = AsyncMock(return_value=MagicMock(exit_code=0, stdout="fallback_ok", stderr=""))

    env = Tier3DockerEnvironment(fallback_tier=mock_fallback)
    # Test availability and alias
    assert Tier3DockerContainerEnvironment is Tier3DockerEnvironment

    # Mock docker CLI missing -> should call fallback tier
    with patch.object(env, "is_available", return_value=False):
        res = await env.run_command("echo 123", session_id="test_sess_1")
        assert res.stdout == "fallback_ok"
        mock_fallback.run_command.assert_awaited_once()

    # Mock docker CLI present with mock subprocess
    with patch.object(env, "is_available", return_value=True):
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock container running check returning empty (needs create)
            proc_check = MagicMock()
            proc_check.communicate = AsyncMock(return_value=(b"", b""))
            proc_check.returncode = 0

            # Mock create run container
            proc_create = MagicMock()
            proc_create.communicate = AsyncMock(return_value=(b"container_id_123\n", b""))
            proc_create.returncode = 0

            # Mock command execution via exec
            proc_cmd = MagicMock()
            proc_cmd.communicate = AsyncMock(return_value=(b"result_inside_container\n", b""))
            proc_cmd.returncode = 0

            mock_exec.side_effect = [proc_check, proc_create, proc_create, proc_cmd]

            outcome = await env.run_command("python test.py", session_id="session_alpha")
            assert outcome.exit_code == 0
            assert "result_inside_container" in outcome.stdout
            assert "session_alpha" in env._active_containers

            # Test cleanup
            with patch.object(env, "stop_container", new_callable=AsyncMock) as mock_stop:
                env.cleanup()
                await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_delegate_tool_lifecycle():
    _ACTIVE_SUBAGENTS.clear()

    # 1. Spawn a subagent
    spawn_input = DelegateTaskInput(
        task="Audit EURUSD trend momentum",
        role="quant_researcher",
        action="spawn",
        isolated_worktree=False,
    )
    spawn_res = await handle_delegate_task(spawn_input)
    assert "[SUBAGENT EXECUTION COMPLETE]" in spawn_res
    assert "Role: quant_researcher" in spawn_res

    # Extract subagent ID
    sub_id = None
    for line in spawn_res.splitlines():
        if line.startswith("Subagent ID:"):
            sub_id = line.split(":", 1)[1].strip()
            break
    assert sub_id is not None
    assert sub_id in _ACTIVE_SUBAGENTS

    # 2. List subagents
    list_input = DelegateTaskInput(
        task="",
        action="list",
    )
    list_res = await handle_delegate_task(list_input)
    assert "[SUBAGENT REGISTRY" in list_res
    assert sub_id in list_res

    # 3. Status check
    status_input = DelegateTaskInput(
        task="",
        action="status",
        subagent_id=sub_id,
    )
    status_res = await handle_delegate_task(status_input)
    assert "[SUBAGENT STATUS]" in status_res
    assert f"ID: {sub_id}" in status_res

    # 4. Steer subagent
    steer_input = DelegateTaskInput(
        task="Focus on 4H support levels",
        action="steer",
        subagent_id=sub_id,
        steer_message="Focus on 4H support levels",
    )
    steer_res = await handle_delegate_task(steer_input)
    assert "[SUBAGENT STEERED]" in steer_res
    assert "Focus on 4H support levels" in steer_res

    # 5. Cancel subagent
    cancel_input = DelegateTaskInput(
        task="",
        action="cancel",
        subagent_id=sub_id,
    )
    cancel_res = await handle_delegate_task(cancel_input)
    assert "[SUBAGENT CANCELLED]" in cancel_res
    assert _ACTIVE_SUBAGENTS[sub_id]["status"] == "cancelled"
