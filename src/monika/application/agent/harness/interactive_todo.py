"""
Interactive Todo State Machine & Task Progress Tracking.

Enforces disciplined multi-step planning and task execution for Monika:
1. Strict active task invariant: at most one task may be 'in_progress' at any time.
2. Status state transitions: pending -> in_progress -> completed | cancelled.
3. Formatted scaffold generation for dynamic turn injection.
4. Completion auditing to prevent premature finish before all tasks are completed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger("TradingAgent.Harness.InteractiveTodo")

TodoStatus = Literal["pending", "in_progress", "completed", "cancelled"]
VALID_STATUSES: set[str] = {"pending", "in_progress", "completed", "cancelled"}


@dataclass
class TodoItem:
    id: str
    content: str
    status: TodoStatus = "pending"

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "content": self.content, "status": self.status}


@dataclass
class TodoListState:
    """
    Manages active task checklist state across turns.
    Enforces that an agent focuses on exactly one in-progress task at a time.
    """

    todos: List[TodoItem] = field(default_factory=list)

    def has_todos(self) -> bool:
        return len(self.todos) > 0

    def has_items(self) -> bool:
        return len(self.todos) > 0

    def has_active_todos(self) -> bool:
        return any(t.status in ("pending", "in_progress") for t in self.todos)

    def get_in_progress_task(self) -> Optional[TodoItem]:
        for t in self.todos:
            if t.status == "in_progress":
                return t
        return None

    def all_completed(self) -> bool:
        if not self.todos:
            return True
        return all(t.status in ("completed", "cancelled") for t in self.todos)

    def update_todos(self, raw_todos: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Replaces and validates the entire todo list with whole-list replacement.
        Enforces:
        - At most one task may be 'in_progress'.
        - Content must be non-empty.
        - Status must be valid.
        """
        if not isinstance(raw_todos, list):
            return False, "Input must be a list of todo item dictionaries."

        new_items: List[TodoItem] = []
        active_count = 0

        for i, item in enumerate(raw_todos, start=1):
            if not isinstance(item, dict):
                return False, f"Todo item {i} must be a dictionary."

            content = str(item.get("content") or "").strip()
            if not content:
                return False, f"Todo item {i} has empty 'content'."

            status = str(item.get("status") or "pending").strip().lower()
            if status not in VALID_STATUSES:
                return (
                    False,
                    f"Todo item {i} has invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}.",
                )

            if status == "in_progress":
                active_count += 1

            todo_id = str(item.get("id") or f"task_{i}")
            new_items.append(TodoItem(id=todo_id, content=content, status=status))  # type: ignore[arg-type]

        if active_count > 1:
            return (
                False,
                f"Invalid todos: At most one task may be 'in_progress' at any time (got {active_count}). "
                f"Keep exactly one active task in progress.",
            )

        self.todos = new_items
        logger.info(
            f"[TodoListState] Updated todos: {len(self.todos)} total, "
            f"{sum(1 for t in self.todos if t.status == 'completed')} completed, "
            f"{active_count} in_progress."
        )
        return True, f"Successfully updated {len(self.todos)} task(s)."

    def format_scaffold(self) -> str:
        """Renders markdown checklist scaffold for prompt context."""
        if not self.todos:
            return ""

        lines = ["[ACTIVE TASK LIST - PLAN CHECKLIST]"]
        status_icons = {
            "pending": "[ ]",
            "in_progress": "[>] IN_PROGRESS:",
            "completed": "[x]",
            "cancelled": "[-]",
        }
        for t in self.todos:
            icon = status_icons.get(t.status, "[ ]")
            lines.append(f"- {icon} {t.content}")

        lines.append(
            "\nDiscipline Rule: Focus on the single in_progress task. Mark completed via todo_write before moving to next."
        )
        return "\n".join(lines)

    def to_dict_list(self) -> List[Dict[str, str]]:
        return [t.to_dict() for t in self.todos]

    def audit_completion(self) -> Tuple[bool, str]:
        """
        Audits whether all tasks in the TODO list are completed or cancelled.
        Returns (True, "All tasks completed.") if no pending or in_progress tasks remain.
        """
        if not self.todos:
            return True, "No tasks in TODO list."

        incomplete = [t for t in self.todos if t.status in ("pending", "in_progress")]
        if incomplete:
            items_desc = ", ".join(f"'{t.content}' ({t.status})" for t in incomplete)
            return False, f"Incomplete tasks remain: {items_desc}. Finish or cancel all tasks before ending cycle."

        return True, "All tasks in TODO list are finished."

    def reset(self) -> None:
        """Clear all tracked todo items at the start of a new agent run."""
        self.todos.clear()
