# ==============================================================================
# File: analysis/tools/domain/kanban_tools.py
# ==============================================================================

"""
Autonomous Kanban Task Board Management Tool.
Institutional-grade engine turn protection architecture.

Enables Monika and autonomous agents to organize, prioritize, and track
multi-step analysis, debugging, and trading workflows across columns.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.Kanban")

_KANBAN_DIR = Path("trading-agent/data")
_KANBAN_FILE = _KANBAN_DIR / "kanban_board.json"

VALID_COLUMNS = frozenset({"backlog", "in_progress", "review", "done"})


class KanbanBoardInput(BaseModel):
    """Schema for managing autonomous kanban board tasks."""
    action: str = Field(
        ...,
        description="Action to perform: 'list', 'add', 'move', or 'delete'."
    )
    task_id: Optional[str] = Field(
        None,
        description="Unique identifier of the task (required for 'move' and 'delete')."
    )
    title: Optional[str] = Field(
        None,
        description="Short summary or title of the task (required for 'add')."
    )
    column: Optional[str] = Field(
        "backlog",
        description="Column target: 'backlog', 'in_progress', 'review', or 'done'."
    )
    priority: Optional[str] = Field(
        "medium",
        description="Priority: 'low', 'medium', 'high', or 'urgent'."
    )
    notes: Optional[str] = Field(
        None,
        description="Detailed description, checklist, or findings."
    )


def _load_board() -> Dict[str, List[Dict[str, Any]]]:
    """Load kanban board data from disk."""
    if not _KANBAN_FILE.exists():
        return {col: [] for col in VALID_COLUMNS}
    try:
        data = json.loads(_KANBAN_FILE.read_text(encoding="utf-8"))
        for col in VALID_COLUMNS:
            if col not in data:
                data[col] = []
        return data
    except Exception as e:
        logger.warning(f"[KanbanTool] Failed to read board, returning empty: {e}")
        return {col: [] for col in VALID_COLUMNS}


def _save_board(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Save kanban board data to disk atomically."""
    _KANBAN_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _KANBAN_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp_path.replace(_KANBAN_FILE)


@unified_tool_registry.register(
    name="manage_kanban_board",
    category="TASK_MANAGEMENT",
    input_model=KanbanBoardInput,
)
async def handle_manage_kanban_board(
    params: KanbanBoardInput,
    context: Optional[Any] = None,
) -> str:
    """Execute Kanban board state manipulation."""
    action = params.action.lower().strip()
    board = _load_board()

    if action == "list":
        lines = ["# Kanban Board Status\n"]
        for col in ["backlog", "in_progress", "review", "done"]:
            tasks = board.get(col, [])
            lines.append(f"## {col.upper()} ({len(tasks)})")
            if not tasks:
                lines.append("  *(empty)*")
            for t in tasks:
                lines.append(f"- `[{t['id']}]` **{t['title']}** (Priority: {t.get('priority', 'medium')})")
                if t.get("notes"):
                    lines.append(f"  Notes: {t['notes']}")
            lines.append("")
        return "\n".join(lines)

    elif action == "add":
        if not params.title:
            return "Error: 'title' is required when adding a new task."
        target_col = (params.column or "backlog").lower().strip()
        if target_col not in VALID_COLUMNS:
            return f"Error: Invalid column '{target_col}'. Must be one of {sorted(VALID_COLUMNS)}"

        task_id = f"task_{secrets.token_hex(3)}"
        task = {
            "id": task_id,
            "title": params.title.strip(),
            "priority": (params.priority or "medium").lower().strip(),
            "notes": params.notes or "",
            "created_at": time.time(),
        }
        board[target_col].append(task)
        _save_board(board)
        return f"Task '{task_id}' successfully added to column '{target_col}': {params.title}"

    elif action == "move":
        if not params.task_id:
            return "Error: 'task_id' is required to move a task."
        target_col = (params.column or "done").lower().strip()
        if target_col not in VALID_COLUMNS:
            return f"Error: Invalid column '{target_col}'. Must be one of {sorted(VALID_COLUMNS)}"

        target_task = None
        for col, tasks in board.items():
            for t in list(tasks):
                if t["id"] == params.task_id:
                    target_task = t
                    tasks.remove(t)
                    break
            if target_task:
                break

        if not target_task:
            return f"Error: Task with ID '{params.task_id}' was not found on the board."

        if params.notes:
            target_task["notes"] = f"{target_task.get('notes', '')}\n[Update]: {params.notes}".strip()

        board[target_col].append(target_task)
        _save_board(board)
        return f"Task '{params.task_id}' ('{target_task['title']}') moved to '{target_col}'."

    elif action == "delete":
        if not params.task_id:
            return "Error: 'task_id' is required to delete a task."

        deleted = False
        for col, tasks in board.items():
            for t in list(tasks):
                if t["id"] == params.task_id:
                    tasks.remove(t)
                    deleted = True
                    break
            if deleted:
                break

        if not deleted:
            return f"Error: Task with ID '{params.task_id}' not found."

        _save_board(board)
        return f"Task '{params.task_id}' deleted from kanban board."

    return f"Error: Unknown action '{action}'. Supported: 'list', 'add', 'move', 'delete'."
