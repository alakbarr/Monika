"""Safety action reviewer prompt builder with prompt-injection-resistant history filtering.

Filters conversational history to protect the action reviewer:
- Strips 100% of tool results/external outputs (preventing untrusted content injections).
- Strips assistant free-text reasoning/thoughts.
- Formats structured user instructions, system context, prior tool calls, and the pending action.
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any


def build_filtered_review_history(
    messages: Sequence[dict[str, Any]],
    pending_tool_name: str,
    pending_args: dict[str, Any],
) -> str:
    """Build filtered history and pending action XML for safety review.

    Completely excludes tool results and assistant free-text reasoning to prevent
    indirect prompt injection attacks against the action reviewer model.
    """
    history_lines: list[str] = ["<FILTERED_HISTORY>"]

    for msg in messages:
        role = msg.get("role")
        # Strip all tool result content unconditionally
        if role in ("tool", "tool/result"):
            continue

        if role in ("user", "system", "developer"):
            content = str(msg.get("content") or "").strip()
            history_lines.append(f'<message role="{role}">\n{content}\n</message>')
        elif role == "assistant":
            # For assistant messages, include ONLY structured tool calls, stripping free-text reasoning
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                call_lines: list[str] = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        fn_obj = tc.get("function")
                        if isinstance(fn_obj, dict):
                            call_name = fn_obj.get("name")
                            args_raw = fn_obj.get("arguments")
                        else:
                            call_name = tc.get("name")
                            args_raw = tc.get("arguments")

                        if isinstance(args_raw, str):
                            try:
                                args_clean = json.loads(args_raw)
                            except Exception:
                                args_clean = {"raw": args_raw}
                        elif isinstance(args_raw, dict):
                            args_clean = args_raw
                        else:
                            args_clean = {}

                        args_json = json.dumps(args_clean, sort_keys=True, separators=(",", ":"))
                        call_lines.append(f'<tool_call name="{call_name}">{args_json}</tool_call>')

                if call_lines:
                    calls_formatted = "\n".join(call_lines)
                    history_lines.append(f'<message role="assistant">\n{calls_formatted}\n</message>')

    history_lines.append("</FILTERED_HISTORY>")

    pending_args_json = json.dumps(pending_args, indent=2, sort_keys=True)
    pending_section = (
        f"<PENDING_ACTION>\n"
        f"<tool_name>{pending_tool_name}</tool_name>\n"
        f"<arguments>\n{pending_args_json}\n</arguments>\n"
        f"</PENDING_ACTION>"
    )

    return "\n\n".join(["\n".join(history_lines), pending_section])
