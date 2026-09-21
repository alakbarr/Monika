"""
Tool Execution Loop Guard.

Prevents infinite agent oscillation and token-draining loops by tracking consecutive
identical tool calls with canonical argument sorting and SHA-256 hashing.
Enforces stepped escalation thresholds: gentle (3), insistent (5), force-stop (8).
"""

import hashlib
import json
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple


def _sort_recursive(obj: Any) -> Any:
    """Recursively sort dictionary keys and normalize lists for deterministic serialization."""
    if isinstance(obj, dict):
        return {k: _sort_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_sort_recursive(v) for v in obj]
    return obj


def canonical_tool_hash(tool_name: str, args: Any) -> str:
    """Generate SHA-256 hash from canonicalized tool name and JSON argument payload."""
    try:
        sorted_args = _sort_recursive(args) if isinstance(args, (dict, list)) else str(args)
        payload = json.dumps(
            {"tool": tool_name, "args": sorted_args},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
    except Exception:
        payload = f"{tool_name}:{str(args)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ToolLoopGuard:
    """
    Detects and escalates warnings when the agent invokes identical tool calls repeatedly.
    """

    THRESHOLDS = (3, 5, 8)
    PREVIEW_CHARS = 400

    def __init__(self):
        self._consecutive_counts: Dict[str, int] = defaultdict(int)
        self._last_hash: Optional[str] = None
        self._last_tool_name: Optional[str] = None

    def check(self, tool_name: str, args: Any) -> Tuple[bool, Optional[str]]:
        """
        Check tool invocation against repetition history.

        Returns:
            (is_force_stop, reminder_message)
            - is_force_stop: True if threshold >= 8 is reached (must abort).
            - reminder_message: Non-empty warning to be injected if threshold is hit.
        """
        current_hash = canonical_tool_hash(tool_name, args)

        if current_hash == self._last_hash:
            self._consecutive_counts[current_hash] += 1
            count = self._consecutive_counts[current_hash]
        else:
            self._consecutive_counts.clear()
            self._last_hash = current_hash
            self._last_tool_name = tool_name
            self._consecutive_counts[current_hash] = 1
            count = 1

        # Evaluate escalation thresholds
        if count >= 8:
            msg = (
                f"[FORCE STOP] You have called `{tool_name}` {count} consecutive times "
                f"with identical arguments. Further execution of this tool call is blocked. "
                f"You MUST synthesize your findings or call your required final submission tool immediately."
            )
            return True, msg

        if count == 5:
            preview = json.dumps(args, ensure_ascii=False, default=str)[:self.PREVIEW_CHARS]
            msg = (
                f"[INSISTENT WARNING] You called `{tool_name}` 5 consecutive times with identical parameters: "
                f"{preview}. This indicates an unproductive loop. Inspect the previous output and change strategy."
            )
            return False, msg

        if count == 3:
            msg = (
                f"[LOOP ADVISORY] Note: `{tool_name}` was called 3 times consecutively with identical arguments. "
                f"Please verify if you already have sufficient data to reach a conclusion."
            )
            return False, msg

        return False, None

    def reset(self) -> None:
        """Reset consecutive counter for fresh turns or new stages."""
        self._consecutive_counts.clear()
        self._last_hash = None
        self._last_tool_name = None
