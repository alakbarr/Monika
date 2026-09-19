"""
Four-pass message history alternation cleaner and repair engine for provider API dispatch.
"""

import copy
from typing import Any, Dict, List, Set


def repair_message_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enforces strict role alternation and tool-result pairing integrity across message sequences.
    1. Merge adjacent assistant turns
    2. Drop orphaned tool results (whose call ID does not exist in prior assistant calls)
    3. Prune unanswered tool_calls in assistant messages
    4. Merge adjacent user turns
    """
    if not messages:
        return []

    repaired = [copy.deepcopy(m) for m in messages if isinstance(m, dict)]

    repaired = _merge_consecutive_roles(repaired, "assistant")
    repaired = _drop_orphaned_tool_results(repaired)
    repaired = _prune_unanswered_tool_calls(repaired)
    repaired = _merge_consecutive_roles(repaired, "user")

    return repaired


def _merge_consecutive_roles(msgs: List[Dict[str, Any]], target_role: str) -> List[Dict[str, Any]]:
    """Merges consecutive messages sharing target_role into a unified content block."""
    merged: List[Dict[str, Any]] = []

    for msg in msgs:
        role = msg.get("role")
        if merged and merged[-1].get("role") == target_role and role == target_role:
            prev = merged[-1]
            prev_content = prev.get("content", "")
            curr_content = msg.get("content", "")

            # If content is string
            if isinstance(prev_content, str) and isinstance(curr_content, str):
                prev["content"] = f"{prev_content}\n\n{curr_content}".strip()
            elif isinstance(prev_content, list) and isinstance(curr_content, list):
                prev["content"] = prev_content + curr_content
            elif isinstance(prev_content, list) and isinstance(curr_content, str):
                prev["content"].append({"type": "text", "text": curr_content})
            elif isinstance(prev_content, str) and isinstance(curr_content, list):
                prev["content"] = [{"type": "text", "text": prev_content}] + curr_content

            # Combine tool_calls if present
            if "tool_calls" in msg:
                if "tool_calls" not in prev:
                    prev["tool_calls"] = []
                prev["tool_calls"].extend(msg["tool_calls"])
        else:
            merged.append(msg)

    return merged


def _drop_orphaned_tool_results(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Discards tool result messages whose calling ID was pruned or never emitted."""
    valid_tool_ids: Set[str] = set()

    for msg in msgs:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                if isinstance(tc, dict) and tc.get("id"):
                    valid_tool_ids.add(str(tc["id"]))
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                        valid_tool_ids.add(str(block["id"]))

    cleaned: List[Dict[str, Any]] = []
    for msg in msgs:
        role = msg.get("role")
        if role == "tool":
            tid = msg.get("tool_call_id")
            if tid and str(tid) not in valid_tool_ids:
                continue
        elif role == "user" and isinstance(msg.get("content"), list):
            # Anthropic style tool_result inside user role
            filtered_blocks = []
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tid = block.get("tool_use_id")
                    if tid and str(tid) not in valid_tool_ids:
                        continue
                filtered_blocks.append(block)
            msg["content"] = filtered_blocks

        cleaned.append(msg)

    return cleaned


def _prune_unanswered_tool_calls(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strips tool_calls from assistant messages if no corresponding tool result was received."""
    answered_tool_ids: Set[str] = set()

    for msg in msgs:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            answered_tool_ids.add(str(msg["tool_call_id"]))
        elif msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id"):
                    answered_tool_ids.add(str(block["tool_use_id"]))

    for msg in msgs:
        if msg.get("role") == "assistant":
            if "tool_calls" in msg and isinstance(msg["tool_calls"], list):
                msg["tool_calls"] = [
                    tc for tc in msg["tool_calls"] if isinstance(tc, dict) and str(tc.get("id")) in answered_tool_ids
                ]
                if not msg["tool_calls"]:
                    del msg["tool_calls"]
            if isinstance(msg.get("content"), list):
                msg["content"] = [
                    b for b in msg["content"]
                    if not (isinstance(b, dict) and b.get("type") == "tool_use" and str(b.get("id")) not in answered_tool_ids)
                ]

    return msgs
