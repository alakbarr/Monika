# ==============================================================================
# File: analysis/tools/domain/todo_tool.py
# ==============================================================================

"""
Structured Task & Checklist Tracking Tool for Complex Plans.
Enables Monika to maintain an explicit, stateful task list during multi-step
workflows, code refactors, trading strategy research, and general problem solving.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.Todo")

DEFAULT_TODO_FILE = "data/todos.json"


class TodoActionInput(BaseModel):
    """Schema for managing task checklist items."""
    action: str = Field(
        ...,
        description="Action to perform: 'add', 'list', 'update', or 'clear'."
    )
    title: Optional[str] = Field(
        None,
        description="Title/description of the task (required for 'add')."
    )
    task_id: Optional[int] = Field(
        None,
        description="Numeric ID of the task (required for 'update')."
    )
    status: Optional[str] = Field(
        None,
        description="New status for 'update': 'pending', 'in_progress', 'completed', or 'cancelled'."
    )
    priority: Optional[str] = Field(
        "medium",
        description="Priority level: 'low', 'medium', 'high', or 'critical'."
    )


@dataclass
class TodoItem:
    id: int
    title: str
    status: str
    priority: str
    created_at: float
    updated_at: float


class TodoTracker:
    """Manages persistent checklist items on disk."""

    def __init__(self, file_path: str = DEFAULT_TODO_FILE):
        self.file_path = file_path
        self._todos: Dict[int, TodoItem] = {}
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        t = TodoItem(**item)
                        self._todos[t.id] = t
                        if t.id >= self._next_id:
                            self._next_id = t.id + 1
            except Exception as e:
                logger.debug(f"[TodoTracker] Could not load todos: {e}")

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([asdict(t) for t in self._todos.values()], f, indent=2)
        except Exception as e:
            logger.debug(f"[TodoTracker] Could not save todos: {e}")

    def add(self, title: str, priority: str = "medium") -> TodoItem:
        item = TodoItem(
            id=self._next_id,
            title=title,
            status="pending",
            priority=priority.lower(),
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._todos[item.id] = item
        self._next_id += 1
        self._save()
        return item

    def list_items(self, status: Optional[str] = None) -> List[TodoItem]:
        items = list(self._todos.values())
        if status:
            s_clean = status.lower().strip()
            items = [i for i in items if i.status == s_clean]
        items.sort(key=lambda x: x.id)
        return items

    def update(self, task_id: int, status: str) -> Optional[TodoItem]:
        item = self._todos.get(task_id)
        if not item:
            return None
        item.status = status.lower().strip()
        item.updated_at = time.time()
        self._save()
        return item

    def clear_completed(self) -> int:
        to_delete = [t.id for t in self._todos.values() if t.status in ("completed", "cancelled")]
        for tid in to_delete:
            del self._todos[tid]
        self._save()
        return len(to_delete)


_tracker = TodoTracker()


@unified_tool_registry.register(
    name="manage_todo",
    category="TASK_MANAGEMENT",
    input_model=TodoActionInput,
)
async def handle_manage_todo(
    params: TodoActionInput,
    context: Optional[Any] = None,
) -> Dict[str, Any]:
    """Manages the agent's active plan checklist and task statuses."""
    act = params.action.lower().strip()

    if act == "add":
        if not params.title:
            return {"success": False, "error": "Title is required to add a todo item."}
        item = _tracker.add(params.title, priority=params.priority or "medium")
        return {
            "success": True,
            "message": f"Added task #{item.id}: '{item.title}'",
            "task": asdict(item),
        }

    elif act == "list":
        items = _tracker.list_items(status=params.status)
        return {
            "success": True,
            "total": len(items),
            "tasks": [asdict(i) for i in items],
        }

    elif act == "update":
        if params.task_id is None:
            return {"success": False, "error": "task_id is required to update a task."}
        if not params.status:
            return {"success": False, "error": "status is required to update a task."}

        item = _tracker.update(params.task_id, params.status)
        if not item:
            return {"success": False, "error": f"Task #{params.task_id} not found."}
        return {
            "success": True,
            "message": f"Task #{item.id} updated to status '{item.status}'",
            "task": asdict(item),
        }

    elif act == "clear":
        cleared_count = _tracker.clear_completed()
        return {
            "success": True,
            "message": f"Cleared {cleared_count} completed/cancelled tasks.",
        }

    return {"success": False, "error": f"Unknown action '{act}'. Use 'add', 'list', 'update', or 'clear'."}
