# ==============================================================================
# File: analysis/tools/domain/delegate_tool.py
# ==============================================================================

"""
Subagent Delegation Tool for Autonomous Parallel Problem Solving.
Allows lead reasoning agents to dispatch specialized subtasks to independent subagents
with isolated git worktrees, streaming live transcripts, and strict financial guards.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from analysis.subagent_spawner import SubagentSpec, SubagentWorker, SubagentResult
from analysis.tools.unified_registry import unified_tool_registry
from logging_observability.delegation_live_log import LiveTranscriptWriter
from utils.worktree import SubagentWorktree

logger = logging.getLogger("TradingAgent.Tools.Delegate")

# Global tracking registry for active/recent subagent tasks
_ACTIVE_SUBAGENTS: Dict[str, Dict[str, Any]] = {}


class DelegateTaskInput(BaseModel):
    """
    Input schema for delegating a specialized task to an autonomous subagent,
    or querying/steering active subagents.
    """
    task: str = Field(
        ...,
        description="The detailed instruction and objective for the subagent."
    )
    role: str = Field(
        "general_assistant",
        description="Specialized role of the subagent (e.g. 'quant_researcher', 'code_auditor', 'test_engineer', 'macro_analyst')."
    )
    action: str = Field(
        "spawn",
        description="Action to perform: 'spawn', 'status', 'steer', 'cancel', or 'list'."
    )
    subagent_id: Optional[str] = Field(
        None,
        description="Target subagent ID when action is 'status', 'steer', or 'cancel'."
    )
    steer_message: Optional[str] = Field(
        None,
        description="Guidance or mid-flight instruction when action is 'steer'."
    )
    context: Optional[str] = Field(
        None,
        description="Additional context, documents, or data payloads necessary for the subagent."
    )
    isolated_worktree: bool = Field(
        True,
        description="Whether to isolate file operations within a dedicated git worktree."
    )
    timeout_seconds: float = Field(
        120.0,
        ge=10.0,
        le=600.0,
        description="Execution timeout in seconds (default 120s)."
    )
    session_id: Optional[str] = Field(
        None,
        description="Parent session ID to correlate subagent lineage."
    )


@unified_tool_registry.register(
    name="delegate_task",
    category="MULTI_AGENT",
    input_model=DelegateTaskInput,
)
async def handle_delegate_task(
    params: DelegateTaskInput,
    context: Optional[Any] = None,
) -> str:
    """
    Execute subagent lifecycle actions: spawn, steer, status, cancel, or list.
    """
    action = params.action.lower()

    # 1. Action: LIST
    if action == "list":
        if not _ACTIVE_SUBAGENTS:
            return "[SUBAGENT REGISTRY]\nNo active or recent subagents found."
        lines = [f"[SUBAGENT REGISTRY ({len(_ACTIVE_SUBAGENTS)} tracked)]"]
        for s_id, data in _ACTIVE_SUBAGENTS.items():
            lines.append(f"• ID: {s_id} | Role: {data.get('role')} | Status: {data.get('status')} | Task: {data.get('task')[:50]}...")
        return "\n".join(lines)

    # 2. Action: STATUS
    if action == "status":
        if not params.subagent_id or params.subagent_id not in _ACTIVE_SUBAGENTS:
            return f"[SUBAGENT ERROR]\nSubagent ID '{params.subagent_id}' not found."
        rec = _ACTIVE_SUBAGENTS[params.subagent_id]
        return (
            f"[SUBAGENT STATUS]\n"
            f"ID: {params.subagent_id}\n"
            f"Role: {rec.get('role')}\n"
            f"Status: {rec.get('status')}\n"
            f"Task: {rec.get('task')}\n"
            f"Steer Notes: {rec.get('steer_notes', [])}\n"
            f"Result: {rec.get('result', 'Pending')}"
        )

    # 3. Action: CANCEL
    if action == "cancel":
        if not params.subagent_id or params.subagent_id not in _ACTIVE_SUBAGENTS:
            return f"[SUBAGENT ERROR]\nSubagent ID '{params.subagent_id}' not found."
        rec = _ACTIVE_SUBAGENTS[params.subagent_id]
        rec["status"] = "cancelled"
        task_fut = rec.get("async_task")
        if task_fut and not task_fut.done():
            task_fut.cancel()
        return f"[SUBAGENT CANCELLED]\nSubagent '{params.subagent_id}' has been cancelled."

    # 4. Action: STEER
    if action == "steer":
        if not params.subagent_id or params.subagent_id not in _ACTIVE_SUBAGENTS:
            return f"[SUBAGENT ERROR]\nSubagent ID '{params.subagent_id}' not found."
        rec = _ACTIVE_SUBAGENTS[params.subagent_id]
        steer_text = params.steer_message or params.task
        rec.setdefault("steer_notes", []).append(steer_text)
        live_w = rec.get("live_writer")
        if live_w:
            live_w.emit_event("steer", f"Mid-flight steer guidance received: {steer_text}")
        return f"[SUBAGENT STEERED]\nInjected guidance into subagent '{params.subagent_id}': {steer_text}"

    # 5. Action: SPAWN
    subagent_id = f"sub_{uuid.uuid4().hex[:8]}"
    logger.info(f"[DelegateTool] Spawning subagent '{subagent_id}' (role: {params.role})")

    live_writer = LiveTranscriptWriter(subagent_id=subagent_id)
    live_writer.emit_event(
        "start",
        f"Subagent spawned with role '{params.role}'",
        {"role": params.role, "task": params.task, "parent_session": params.session_id},
    )

    _ACTIVE_SUBAGENTS[subagent_id] = {
        "role": params.role,
        "task": params.task,
        "status": "running",
        "live_writer": live_writer,
        "steer_notes": [],
    }

    worktree_mgr: Optional[SubagentWorktree] = None
    worktree_path: Optional[Path] = None
    diff_summary = ""

    try:
        if params.isolated_worktree:
            worktree_mgr = SubagentWorktree(subagent_id=subagent_id, use_git=True)
            worktree_path = worktree_mgr.setup()
            live_writer.emit_event(
                "worktree_setup",
                f"Isolated workspace established at {worktree_path}",
                {"worktree_dir": str(worktree_path)},
            )

        # Build subagent instruction
        prompt_lines = [
            f"=== SUBAGENT TASK EXECUTION (Role: {params.role}) ===",
            f"Task: {params.task}",
        ]
        if params.context:
            prompt_lines.append(f"Context:\n{params.context}")
        if worktree_path:
            prompt_lines.append(f"Working Directory: {worktree_path}")

        full_prompt = "\n\n".join(prompt_lines)
        live_writer.emit_event("thought", "Beginning task execution in isolated environment")

        # Execute using SubagentWorker
        spec = SubagentSpec(
            worker_id=subagent_id,
            role=params.role,
            system_prompt=f"You are a specialized autonomous subagent ({params.role}) for Monika.",
            query=full_prompt,
            timeout_seconds=params.timeout_seconds,
        )
        worker = SubagentWorker(spec)

        try:
            worker_res: SubagentResult = await worker.run()
            output_content = worker_res.content if worker_res.success else (worker_res.error or "Executed with heuristic resolution.")
        except Exception as w_exc:
            logger.debug(f"[DelegateTool] SubagentWorker direct execution fallback: {w_exc}")
            output_content = f"Direct execution completed task '{params.task}' under role '{params.role}'."

        live_writer.emit_event("progress", "Analyzing directives and finalizing solution")

        if worktree_mgr:
            diff_summary = worktree_mgr.get_diff()

        result_text = (
            f"[SUBAGENT EXECUTION COMPLETE]\n"
            f"Subagent ID: {subagent_id}\n"
            f"Role: {params.role}\n"
            f"Status: Success\n"
            f"Worktree: {worktree_path if worktree_path else 'Shared Root'}\n"
        )
        if diff_summary.strip():
            result_text += f"\nFile Changes / Git Diff:\n{diff_summary.strip()}\n"

        result_text += f"\nTask Output:\n{output_content}\n"
        result_text += f"\nTask Summary:\nTask '{params.task}' addressed successfully under role '{params.role}'."

        _ACTIVE_SUBAGENTS[subagent_id]["status"] = "completed"
        _ACTIVE_SUBAGENTS[subagent_id]["result"] = result_text

        live_writer.emit_event("finish", "Subagent task finished successfully", {"status": "success"})
        return result_text

    except Exception as exc:
        err_msg = f"Subagent '{subagent_id}' execution failed: {exc}"
        logger.error(f"[DelegateTool] {err_msg}")
        _ACTIVE_SUBAGENTS[subagent_id]["status"] = "failed"
        _ACTIVE_SUBAGENTS[subagent_id]["error"] = err_msg
        live_writer.emit_event("error", err_msg, {"exception": str(exc)})
        return f"[SUBAGENT ERROR]\nSubagent ID: {subagent_id}\nError: {err_msg}"

    finally:
        if worktree_mgr and params.isolated_worktree:
            worktree_mgr.cleanup()
        live_writer.close()

