"""
Four-pass message history alternation cleaner and repair engine for provider API dispatch.
Supports non-destructive unanswered tool call recovery and cross-model reasoning signature translation.
"""

import copy
from typing import Any, Dict, List, Optional, Set

TOOL_OUTCOME_UNKNOWN_MSG = (
    "Tool execution was interrupted before a result was recorded; "
    "whether the call took effect is unknown. Reconcile broker/system state before retrying non-idempotent actions."
)
TOOL_NOT_STARTED_MSG = "Tool execution did not start before the previous turn ended."


def repair_message_history(
    messages: List[Dict[str, Any]],
    close_unanswered: bool = False,
    executed_call_ids: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Enforces strict role alternation and tool-result pairing integrity across message sequences.
    1. Merge adjacent assistant turns (preserving reasoning and signatures)
    2. Drop orphaned tool results (whose call ID does not exist in prior assistant calls)
    3. Recover unanswered tool calls:
       - If close_unanswered=True: non-destructively inserts synthetic error tool results (KV cache safe)
       - If close_unanswered=False: prunes unanswered tool_calls from assistant messages
    4. Merge adjacent user turns
    """
    if not messages:
        return []

    repaired = [copy.deepcopy(m) for m in messages if isinstance(m, dict)]

    repaired = _merge_consecutive_roles(repaired, "assistant")
    repaired = _drop_orphaned_tool_results(repaired)
    if close_unanswered:
        repaired = _close_unanswered_tool_calls(repaired, executed_call_ids=executed_call_ids)
    else:
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

            # Preserve assistant thinking fields & cryptographic signatures
            if target_role in ("assistant", "model"):
                prev_rc = prev.get("reasoning_content")
                curr_rc = msg.get("reasoning_content")
                if prev_rc and curr_rc:
                    if isinstance(prev_rc, str) and isinstance(curr_rc, str):
                        prev["reasoning_content"] = f"{prev_rc}\n\n{curr_rc}".strip()
                    elif isinstance(prev_rc, list) and isinstance(curr_rc, list):
                        prev["reasoning_content"] = prev_rc + curr_rc
                    elif isinstance(prev_rc, list) and isinstance(curr_rc, str):
                        prev["reasoning_content"] = prev_rc + [curr_rc]
                    elif isinstance(prev_rc, str) and isinstance(curr_rc, list):
                        prev["reasoning_content"] = [prev_rc] + curr_rc
                elif curr_rc and not prev_rc:
                    prev["reasoning_content"] = curr_rc

                if "thinking_signature" in msg and "thinking_signature" not in prev:
                    prev["thinking_signature"] = msg["thinking_signature"]

                if "thought_signature" in msg and "thought_signature" not in prev:
                    prev["thought_signature"] = msg["thought_signature"]

                prev_rd = prev.get("reasoning_details")
                curr_rd = msg.get("reasoning_details")
                if prev_rd and curr_rd:
                    if isinstance(prev_rd, list) and isinstance(curr_rd, list):
                        prev["reasoning_details"] = prev_rd + curr_rd
                    elif isinstance(prev_rd, dict) and isinstance(curr_rd, dict):
                        m_rd = dict(prev_rd)
                        m_rd.update(curr_rd)
                        prev["reasoning_details"] = m_rd
                elif curr_rd and not prev_rd:
                    prev["reasoning_details"] = curr_rd

                if "_source_provider" in msg and "_source_provider" not in prev:
                    prev["_source_provider"] = msg["_source_provider"]
                if "_source_model" in msg and "_source_model" not in prev:
                    prev["_source_model"] = msg["_source_model"]
        else:
            merged.append(msg)

    return merged


def _drop_orphaned_tool_results(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Discards tool result messages whose calling ID was pruned or never emitted."""
    valid_tool_ids: Set[str] = set()

    for msg in msgs:
        if msg.get("role") in ("assistant", "model"):
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
            if not tid or not str(tid).strip() or str(tid) not in valid_tool_ids:
                continue
        elif role == "user" and isinstance(msg.get("content"), list):
            # Anthropic style tool_result inside user role
            filtered_blocks = []
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tid = block.get("tool_use_id")
                    if not tid or not str(tid).strip() or str(tid) not in valid_tool_ids:
                        continue
                filtered_blocks.append(block)
            if not filtered_blocks:
                continue
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
        if msg.get("role") in ("assistant", "model"):
            if "tool_calls" in msg and isinstance(msg["tool_calls"], list):
                msg["tool_calls"] = [
                    tc for tc in msg["tool_calls"] if isinstance(tc, dict) and str(tc.get("id")) in answered_tool_ids
                ]
                if not msg["tool_calls"]:
                    del msg["tool_calls"]
            if isinstance(msg.get("content"), list):
                msg["content"] = [
                    b
                    for b in msg["content"]
                    if not (
                        isinstance(b, dict)
                        and b.get("type") == "tool_use"
                        and str(b.get("id")) not in answered_tool_ids
                    )
                ]

    cleaned = []
    for msg in msgs:
        if msg.get("role") in ("assistant", "model"):
            content = msg.get("content")
            has_content = bool(content.strip()) if isinstance(content, str) else bool(content)
            has_tool_calls = bool(msg.get("tool_calls"))
            if not has_content and not has_tool_calls:
                continue
        cleaned.append(msg)

    return cleaned


def _close_unanswered_tool_calls(
    msgs: List[Dict[str, Any]],
    executed_call_ids: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Non-destructively closes unanswered tool calls by inserting synthetic error tool results.
    Preserves historical assistant tool_calls/tool_use blocks to avoid busting KV caches.
    """
    exec_ids = executed_call_ids or set()

    # Collect all answered tool IDs across the sequence
    answered_tool_ids: Set[str] = set()
    for msg in msgs:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            answered_tool_ids.add(str(msg["tool_call_id"]))
        elif msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id"):
                    answered_tool_ids.add(str(block["tool_use_id"]))

    result: List[Dict[str, Any]] = []
    i = 0
    n = len(msgs)

    while i < n:
        msg = msgs[i]
        result.append(msg)

        if msg.get("role") in ("assistant", "model"):
            # Check for unanswered OpenAI tool_calls
            unanswered_openai = []
            if "tool_calls" in msg and isinstance(msg["tool_calls"], list):
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict) and tc.get("id"):
                        tid = str(tc["id"])
                        if tid not in answered_tool_ids:
                            unanswered_openai.append(tid)

            # Check for unanswered Anthropic tool_use
            unanswered_anthropic = []
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                        tid = str(block["id"])
                        if tid not in answered_tool_ids:
                            unanswered_anthropic.append(tid)

            # Handle OpenAI synthetic closures
            if unanswered_openai:
                while i + 1 < n and msgs[i + 1].get("role") == "tool":
                    i += 1
                    result.append(msgs[i])

                for tid in unanswered_openai:
                    err_msg = TOOL_OUTCOME_UNKNOWN_MSG if tid in exec_ids else TOOL_NOT_STARTED_MSG
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": tid,
                            "content": err_msg,
                        }
                    )
                    answered_tool_ids.add(tid)

            # Handle Anthropic synthetic closures
            if unanswered_anthropic:
                synth_blocks = []
                for tid in unanswered_anthropic:
                    err_msg = TOOL_OUTCOME_UNKNOWN_MSG if tid in exec_ids else TOOL_NOT_STARTED_MSG
                    synth_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": err_msg,
                            "is_error": True,
                        }
                    )
                    answered_tool_ids.add(tid)

                if i + 1 < n and msgs[i + 1].get("role") == "user" and isinstance(msgs[i + 1].get("content"), list):
                    msgs[i + 1]["content"].extend(synth_blocks)
                else:
                    result.append(
                        {
                            "role": "user",
                            "content": synth_blocks,
                        }
                    )

        i += 1

    return result


def transform_messages_for_target_model(
    messages: List[Dict[str, Any]],
    target_provider: str = "",
    target_model: str = "",
) -> List[Dict[str, Any]]:
    """
    Transforms assistant reasoning and signature blocks when failing over across providers/models.
    Preserves signed thinking and redacted_thinking when replaying against the same (provider, model).
    Strips cryptographic signatures and converts foreign thinking into text blocks on failover.
    """
    if not messages:
        return []

    tgt_prov = (target_provider or "").lower().strip()
    tgt_model = (target_model or "").lower().strip()

    transformed: List[Dict[str, Any]] = []

    for msg in messages:
        if not isinstance(msg, dict):
            transformed.append(msg)
            continue

        if msg.get("role") not in ("assistant", "model"):
            transformed.append(copy.deepcopy(msg))
            continue

        msg_copy = copy.deepcopy(msg)
        src_prov = str(msg_copy.get("_source_provider") or "").lower().strip()
        src_model = str(msg_copy.get("_source_model") or "").lower().strip()

        # Check if target matches source
        is_same_target = True
        if src_prov and tgt_prov and src_prov != tgt_prov:
            is_same_target = False
        elif src_model and tgt_model and src_model != tgt_model:
            is_same_target = False
        elif not src_prov and tgt_prov:
            content = msg_copy.get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "redacted_thinking" and "anthropic" not in tgt_prov:
                            is_same_target = False
                            break
                        if ("thoughtSignature" in b or "thought_signature" in b) and "gemini" not in tgt_prov:
                            is_same_target = False
                            break

        if is_same_target:
            transformed.append(msg_copy)
            continue

        # Failover mode: strip signatures and convert thinking blocks
        msg_copy.pop("thinking_signature", None)
        msg_copy.pop("thought_signature", None)
        msg_copy.pop("thoughtSignature", None)

        content = msg_copy.get("content")
        if isinstance(content, list):
            new_content = []
            for block in content:
                if not isinstance(block, dict):
                    new_content.append(block)
                    continue

                b_type = block.get("type")
                if b_type == "redacted_thinking":
                    # Opaque Anthropic hash cannot be verified by another model - strip completely
                    continue
                elif b_type == "thinking":
                    th_text = str(block.get("thinking") or block.get("text") or "").strip()
                    if th_text:
                        new_content.append({"type": "text", "text": f"[Prior reasoning]: {th_text}"})
                elif b_type == "text":
                    b_copy = {k: v for k, v in block.items() if k not in ("thoughtSignature", "thought_signature")}
                    new_content.append(b_copy)
                else:
                    b_copy = {k: v for k, v in block.items() if k not in ("thoughtSignature", "thought_signature")}
                    new_content.append(b_copy)
            msg_copy["content"] = new_content

        transformed.append(msg_copy)

    return transformed


__all__ = [
    "repair_message_history",
    "transform_messages_for_target_model",
    "TOOL_OUTCOME_UNKNOWN_MSG",
    "TOOL_NOT_STARTED_MSG",
]
