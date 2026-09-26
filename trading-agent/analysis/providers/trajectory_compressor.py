# ==============================================================================
# File: analysis/providers/trajectory_compressor.py
# ==============================================================================

"""
Trajectory Compressor & Boundary Snapping Context Compactor.
Institutional-grade LLM provider orchestration architecture.

Protects against context window overflow while preserving semantic trajectory anchors.
Guarantees preservation of:
  1. Initial system guidance instructions.
  2. The root user prompt defining session intent.
  3. The latest N conversational turns (recency bias) with tail watermarking.
  4. Atomic tool call-response boundary snapping (never orphans tool results).
  5. Compacted intermediate summary injection for loss-minimized semantic retention.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Providers.TrajectoryCompressor")

_THINK_TAG_REGEX = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class TrajectoryCompressor:
    """Intelligent multi-turn transcript compressor with boundary protection and tail watermarking."""

    def __init__(
        self,
        max_tool_output_chars: int = 400,
        preserve_recent_turns: int = 3,
        summarize_intermediate_threshold: int = 4,
    ):
        self.max_tool_output_chars = max_tool_output_chars
        self.preserve_recent_turns = preserve_recent_turns
        self.summarize_intermediate_threshold = summarize_intermediate_threshold

    def _snap_tail_boundary(self, messages: List[Dict[str, Any]], tail_start_idx: int) -> int:
        """
        Snaps tail boundary backward if it lands in the middle of a tool call-response sequence.
        Guarantees that a tool message is never separated from its parent assistant tool_call.
        """
        idx = tail_start_idx
        while idx > 0:
            msg = messages[idx]
            role = msg.get("role")
            # If current message is a tool response, we must include the preceding assistant message
            if role == "tool" or msg.get("tool_call_id"):
                idx -= 1
                continue
            # If preceding message is an assistant with tool_calls that are answered in the tail, include it
            if idx > 0 and messages[idx - 1].get("tool_calls"):
                idx -= 1
                continue
            break
        return max(0, idx)

    def compress_trajectory(
        self,
        messages: List[Dict[str, Any]],
        target_max_messages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compresses transcript messages while preserving system prompts,
        root user intent, and atomic recent conversation turns.
        """
        if not messages or len(messages) <= (self.preserve_recent_turns * 2 + 2):
            return copy.deepcopy(messages)

        # 1. Identify Head Anchors (system messages and first user query)
        head_indices: Set[int] = set()
        first_user_found = False
        for idx, m in enumerate(messages):
            role = m.get("role")
            if role == "system":
                head_indices.add(idx)
            elif role == "user" and not first_user_found:
                head_indices.add(idx)
                first_user_found = True
            elif first_user_found:
                break

        # 2. Identify Tail Anchors (last N user turns) with Atomic Boundary Snapping
        user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        raw_tail_idx = 0
        if len(user_indices) > self.preserve_recent_turns:
            raw_tail_idx = user_indices[-self.preserve_recent_turns]
        else:
            raw_tail_idx = user_indices[0] if user_indices else 0

        # Boundary snap: guarantee no orphaned tool responses
        tail_start_idx = self._snap_tail_boundary(messages, raw_tail_idx)
        tail_indices: Set[int] = set(range(tail_start_idx, len(messages)))

        # 3. Process intermediate messages
        intermediate_msgs: List[Dict[str, Any]] = []
        compressed: List[Dict[str, Any]] = []

        # Emit Head Anchors
        for idx in sorted(head_indices):
            compressed.append(copy.deepcopy(messages[idx]))

        # Collect & compact intermediate messages
        compacted_tools = 0
        for idx in range(len(messages)):
            if idx in head_indices or idx in tail_indices:
                continue

            orig_m = messages[idx]
            m = copy.deepcopy(orig_m)
            content = m.get("content", "")
            role = m.get("role")

            if isinstance(content, str):
                content = _THINK_TAG_REGEX.sub("", content).strip()
                if role == "tool" or m.get("tool_call_id") or "Tool output:" in content:
                    compacted_tools += 1
                    if len(content) > self.max_tool_output_chars:
                        content = (
                            content[:self.max_tool_output_chars]
                            + f"\n... [Output truncated ({len(content)} chars total)]"
                        )
                m["content"] = content

            intermediate_msgs.append(m)

        # 4. If intermediate messages are significant, inject a semantic compaction anchor
        if len(intermediate_msgs) >= self.summarize_intermediate_threshold:
            summary_notice = {
                "role": "system",
                "content": (
                    f"[Context Compaction Notice: Preserved {len(intermediate_msgs)} intermediate turns "
                    f"with {compacted_tools} compacted tool outputs. Recent context continues below.]"
                ),
            }
            compressed.append(summary_notice)

        compressed.extend(intermediate_msgs)

        # 5. Emit Tail Anchors with Watermark metadata
        for idx in sorted(tail_indices):
            m = copy.deepcopy(messages[idx])
            # Attach watermark tag to first tail turn
            if idx == tail_start_idx:
                m["_tail_watermark"] = True
            compressed.append(m)

        logger.debug(
            f"[TrajectoryCompressor] Compressed {len(messages)} messages -> {len(compressed)} "
            f"(head: {len(head_indices)}, inter: {len(intermediate_msgs)}, tail: {len(tail_indices)})"
        )
        return compressed
