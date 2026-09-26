# ==============================================================================
# File: agent/moa_alternation.py
# ==============================================================================

"""
Reactive same-role message alternation merger for MoA and multi-turn LLM requests.

Handles strict-alternation chat APIs (e.g. Anthropic, Mistral, and strict OpenAI-compatible proxies)
by safely merging consecutive same-role messages without mutating inputs in-place.
"""

from __future__ import annotations

import logging
from typing import Any, List, Dict, Tuple

logger = logging.getLogger(__name__)


def destination_key(runtime: Dict[str, Any]) -> Tuple[str, str]:
    """
    (route, model) identity of an LLM destination.
    Uses base_url when specified, else provider slug, paired with model name.
    """
    route = str(runtime.get("base_url") or runtime.get("provider") or "").strip().rstrip("/")
    model = str(runtime.get("model") or "").strip()
    return route, model


def _merge_content(c1: Any, c2: Any) -> Any:
    """Merge two content blocks cleanly."""
    if isinstance(c1, str) and isinstance(c2, str):
        return f"{c1}\n\n{c2}"
    if isinstance(c1, list) and isinstance(c2, list):
        return list(c1) + list(c2)
    if isinstance(c1, list) and isinstance(c2, str):
        return list(c1) + [{"type": "text", "text": c2}]
    if isinstance(c1, str) and isinstance(c2, list):
        return [{"type": "text", "text": c1}] + list(c2)
    return f"{c1}\n\n{c2}"


def merge_same_role_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Returns a new list with adjacent same-role messages merged into one.
    Preserves original objects if no consecutive same-role messages exist.
    """
    if not messages:
        return []

    merged: List[Dict[str, Any]] = []
    changed = False

    for msg in messages:
        if not merged:
            merged.append(dict(msg))
            continue

        prev = merged[-1]
        prev_role = prev.get("role")
        curr_role = msg.get("role")

        if prev_role == curr_role and curr_role in ("user", "assistant"):
            # Merge adjacent user or assistant turns
            merged_content = _merge_content(prev.get("content", ""), msg.get("content", ""))
            new_prev = dict(prev)
            new_prev["content"] = merged_content
            # Merge tool_calls if both assistant messages have tool calls
            prev_tools = prev.get("tool_calls")
            curr_tools = msg.get("tool_calls")
            if prev_tools or curr_tools:
                combined_tools = list(prev_tools or []) + list(curr_tools or [])
                new_prev["tool_calls"] = combined_tools
            merged[-1] = new_prev
            changed = True
        else:
            merged.append(dict(msg))

    return merged if changed else messages


def is_role_alternation_rejection(exc: Exception, runtime: Dict[str, Any] | None = None) -> bool:
    """
    Returns True if an exception message indicates an API error caused by non-alternating roles.
    """
    msg = str(exc).lower()
    alternation_signals = (
        "roles must alternate",
        "consecutive",
        "alternating",
        "user turn must be followed",
        "role_alternation",
        "incorrect role order",
        "two consecutive user messages",
        "two consecutive assistant messages",
    )
    return any(sig in msg for sig in alternation_signals)
