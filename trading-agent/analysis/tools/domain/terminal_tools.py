# ==============================================================================
# File: analysis/tools/domain/terminal_tools.py
# ==============================================================================

"""
Universal Terminal & Process Execution Domain Tools.
Provides controlled command execution, background task supervision, output buffering,
and process handoff across subagents.

Tools registered:
  - terminal: Executes shell command with foreground timeout and background auto-demotion.
  - process_manage: Supervises, inspects, polls, reads logs, or terminates background processes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from analysis.tools.terminal_process_engine import TerminalProcessEngine
from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.TerminalTools")

# Global singleton process engine instance
_TERMINAL_ENGINE = TerminalProcessEngine()


def get_terminal_process_engine() -> TerminalProcessEngine:
    """Return the global TerminalProcessEngine singleton."""
    return _TERMINAL_ENGINE


class TerminalInput(BaseModel):
    """Input parameters for running a command in the terminal."""
    command: str = Field(
        ...,
        description="The shell command string to execute."
    )
    workdir: Optional[str] = Field(
        None,
        description="Working directory for the command. Defaults to workspace root."
    )
    timeout: float = Field(
        60.0,
        ge=1.0,
        le=3600.0,
        description="Command timeout in seconds (default 60s, commands > 600s are automatically demoted to background)."
    )
    background: bool = Field(
        False,
        description="If True, immediately launches the process in the background and returns session_id."
    )
    notify_patterns: List[str] = Field(
        default_factory=list,
        description="List of regex patterns to watch for in stdout/stderr to trigger notifications."
    )
    owner_agent_id: str = Field(
        "main",
        description="Identifier of the executing agent or subagent."
    )


class ProcessManageInput(BaseModel):
    """Input parameters for managing background processes."""
    action: str = Field(
        ...,
        description="Management action to perform: 'poll', 'log', 'kill', 'handoff', or 'list'."
    )
    session_id: Optional[str] = Field(
        None,
        description="Identifier of the target process session (required for 'poll', 'log', 'kill', 'handoff')."
    )
    offset: int = Field(
        0,
        ge=0,
        description="Character offset for paginated log reading (action='log')."
    )
    limit: int = Field(
        5000,
        ge=1,
        le=50000,
        description="Maximum characters to return for log reading (action='log')."
    )
    new_owner_agent_id: Optional[str] = Field(
        None,
        description="Target agent ID when transferring ownership (action='handoff')."
    )


@unified_tool_registry.register(
    name="terminal",
    category="SYSTEM",
    input_model=TerminalInput,
)
async def handle_terminal(
    params: TerminalInput,
    context: Optional[Any] = None,
) -> str:
    """Execute shell command with auto-demotion to background if long-running."""
    result = _TERMINAL_ENGINE.execute(
        command=params.command,
        workdir=params.workdir,
        timeout=int(params.timeout),
        background=params.background,
        notify=params.notify_patterns,
        owner_agent_id=params.owner_agent_id,
    )

    if params.background or result.get("status") == "running_background":
        return json.dumps(result, indent=2)

    if result.get("success"):
        return f"[EXIT CODE 0]\n{result.get('output', '')}"
    else:
        err = result.get("error") or result.get("output") or f"Exited with code {result.get('exit_code')}"
        return f"[FAILED - EXIT {result.get('exit_code')}]\n{err}"


@unified_tool_registry.register(
    name="process_manage",
    category="SYSTEM",
    input_model=ProcessManageInput,
)
async def handle_process_manage(
    params: ProcessManageInput,
    context: Optional[Any] = None,
) -> str:
    """Manage background processes: list, poll, view log, terminate, or transfer ownership."""
    action = params.action.lower().strip()

    if action == "list":
        with _TERMINAL_ENGINE._lock:
            active_list = []
            for sid, p in _TERMINAL_ENGINE._processes.items():
                active_list.append({
                    "session_id": sid,
                    "pid": p.pid,
                    "command": p.command,
                    "is_running": p.is_running,
                    "exit_code": p.exit_code,
                    "owner": p.owner_agent_id,
                })
        return json.dumps(active_list, indent=2)

    if not params.session_id:
        return "[ERROR] 'session_id' is required for action: " + action

    if action == "poll":
        res = _TERMINAL_ENGINE.poll_process(params.session_id)
        return json.dumps(res, indent=2)

    elif action == "log":
        res = _TERMINAL_ENGINE.read_log(
            session_id=params.session_id,
            offset=params.offset,
            limit=params.limit,
        )
        return json.dumps(res, indent=2)

    elif action == "kill":
        res = _TERMINAL_ENGINE.kill_process(params.session_id)
        return json.dumps(res, indent=2)

    elif action == "handoff":
        if not params.new_owner_agent_id:
            return "[ERROR] 'new_owner_agent_id' is required for handoff."
        res = _TERMINAL_ENGINE.handoff_process(
            session_id=params.session_id,
            new_owner_agent_id=params.new_owner_agent_id,
        )
        return json.dumps(res, indent=2)

    return f"[ERROR] Unsupported action '{action}'. Supported: 'list', 'poll', 'log', 'kill', 'handoff'."
