"""Repetition guard monitoring consecutive identical tool invocations.

Provides:
- Canonical argument key serialization with sorted keys.
- Bookkeeping transparency for internal planning tools (todo_write, etc.).
- Graduated reminder interventions at configured streak thresholds.
- Turn-based streak resets on new user messages.
"""

from __future__ import annotations

import json
from typing import Any


def canonicalize_tool_key(tool_name: str, args: Any) -> str:
    """Recursively sort dictionary keys to create deterministic tool invocation signatures."""
    return json.dumps([tool_name, args], sort_keys=True, separators=(",", ":"), default=str)


class RepeatToolGuard:
    """Detects consecutive identical tool calls and injects reminders to break loops."""

    def __init__(
        self,
        thresholds: tuple[int, ...] = (3, 5, 8),
        excluded_tools: frozenset[str] | None = None,
    ) -> None:
        self.thresholds = thresholds
        if excluded_tools is None:
            self.excluded_tools = frozenset({"todo_write", "update_plan", "scratchpad", "manage_todos"})
        else:
            self.excluded_tools = excluded_tools

        self._current_key: str | None = None
        self._count: int = 0

    @property
    def current_streak(self) -> int:
        return self._count

    def observe(self, tool_name: str, args: Any) -> dict[str, Any] | None:
        # Bookkeeping transparency: excluded planning tools are transparent to the streak
        if tool_name in self.excluded_tools:
            return None

        key = canonicalize_tool_key(tool_name, args)
        if key == self._current_key:
            self._count += 1
        else:
            self._current_key = key
            self._count = 1

        if self._count == self.thresholds[0]:
            return {
                "role": "user",
                "content": (
                    f"<system-reminder type=\"repeat-tool-reminder\">Tool '{tool_name}' has been called {self._count} "
                    f"times consecutively with identical arguments. If previous attempts failed or produced "
                    f"expected results, consider an alternative approach or proceeding to next steps.</system-reminder>"
                ),
            }

        if self._count in self.thresholds[1:]:
            args_str = json.dumps(args, default=str, sort_keys=True)[:500]
            return {
                "role": "user",
                "content": (
                    f"<system-reminder type=\"repeat-tool-reminder\">Tool '{tool_name}' has been called {self._count} "
                    f"times consecutively with identical arguments: {args_str}\n"
                    f"You appear to be in a loop. Stop repeating this tool call with these parameters. "
                    f"Change your strategy, verify filesystem state, or ask for user guidance.</system-reminder>"
                ),
            }

        return None

    def reset_on_user_turn(self) -> None:
        """Reset streak counter when a new user turn commences."""
        self._current_key = None
        self._count = 0
