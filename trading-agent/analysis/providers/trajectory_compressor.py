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
  3. The latest N conversational turns (recency bias).
Intermediate turns are cleanly compacted by pruning reasoning think traces and
truncating massive raw tool outputs with informative headers.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Providers.TrajectoryCompressor")

_THINK_TAG_REGEX = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class TrajectoryCompressor:
    """Intelligent multi-turn transcript compressor with boundary protection."""

    def __init__(
        self,
        max_tool_output_chars: int = 400,
        preserve_recent_turns: int = 3,
    ):
        self.max_tool_output_chars = max_tool_output_chars
        self.preserve_recent_turns = preserve_recent_turns

    def compress_trajectory(
        self,
        messages: List[Dict[str, Any]],
        target_max_messages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compresses transcript messages while preserving system prompts,
        root user intent, and recent conversation turns.
        """
        if not messages or len(messages) <= (self.preserve_recent_turns * 2 + 2):
            # Too short to warrant pruning
            return copy.deepcopy(messages)

        compressed: List[Dict[str, Any]] = []

        # 1. Identify Head Anchors (system messages and first user query)
        head_indices = set()
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

        # 2. Identify Tail Anchors (last N turns)
        # Find indices of last N user messages
        user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        tail_start_idx = 0
        if len(user_indices) > self.preserve_recent_turns:
            tail_start_idx = user_indices[-self.preserve_recent_turns]
        else:
            tail_start_idx = user_indices[0] if user_indices else 0

        tail_indices = set(range(tail_start_idx, len(messages)))

        # 3. Process each message
        for idx, orig_m in enumerate(messages):
            m = copy.deepcopy(orig_m)
            content = m.get("content", "")

            if idx in head_indices or idx in tail_indices:
                # Keep completely intact
                compressed.append(m)
            else:
                # Intermediate turn: apply lossy compaction
                role = m.get("role")
                if isinstance(content, str):
                    # 1. Strip think traces from intermediate messages
                    content = _THINK_TAG_REGEX.sub("", content).strip()

                    # 2. Truncate long tool execution results
                    if role == "tool" or m.get("tool_call_id") or "Tool output:" in content:
                        if len(content) > self.max_tool_output_chars:
                            content = (
                                content[:self.max_tool_output_chars]
                                + f"\n... [Output truncated ({len(content)} chars total)]"
                            )

                    m["content"] = content

                compressed.append(m)

        logger.debug(
            f"[TrajectoryCompressor] Compressed {len(messages)} messages (preserved {len(head_indices)} head, {len(tail_indices)} tail)"
        )
        return compressed
