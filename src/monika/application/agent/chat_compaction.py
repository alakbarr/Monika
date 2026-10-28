# ==============================================================================
# Package: monika.application.agent
# File: chat_compaction.py
# ==============================================================================

"""
Micro-Compaction for Cognitive Chat Sessions.

Key invariant: User messages are NEVER summarized (prevents goal drift).
Only assistant responses are compressed into summary markers.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from monika.infrastructure.llm.prompt_compressor import estimate_tokens

logger = logging.getLogger("Monika.Application.ChatCompaction")


class ChatMicroCompactor:
    """Per-turn micro-compaction for unlimited chat conversations."""

    COMPACTION_THRESHOLD = 0.65  # Start compacting at 65% of budget
    ASSISTANT_SUMMARY_MAX_CHARS = 300  # Max chars for compacted assistant turn
    MIN_MESSAGES_TO_COMPACT = 6  # Don't compact if fewer messages

    def __init__(self, max_history_tokens: int = 12000):
        self.max_history_tokens = max_history_tokens

    def compact_history(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Compact chat history, preserving all user messages verbatim.

        Strategy:
        1. Calculate total token usage
        2. If over threshold, find oldest uncompacted assistant message
        3. Replace assistant content with concise summary marker
        4. Repeat until under threshold or all compactable turns done
        """
        if len(messages) < self.MIN_MESSAGES_TO_COMPACT:
            return messages

        total_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        threshold = int(self.max_history_tokens * self.COMPACTION_THRESHOLD)

        if total_tokens <= threshold:
            return messages

        result = [dict(m) for m in messages]

        # Option A: Append-only summary boundary.
        # Do NOT mutate historical assistant turns in-place (maintains KV prompt-cache invariance).
        # Check if an append-only summary boundary has already been injected.
        if any(
            m.get("_summary_boundary") or "[Ringkasan respons sebelumnya:" in str(m.get("content", "")) for m in result
        ):
            return result

        # Summarize older assistant turns into a single append-only summary boundary
        assistant_contents = [
            str(m.get("content", ""))
            for m in result
            if m.get("role") == "assistant" and estimate_tokens(str(m.get("content", ""))) > 50
        ]

        if assistant_contents:
            combined = "\n".join(assistant_contents)
            summary = self._summarize_assistant(combined)
            summary_msg = {
                "role": "assistant",
                "content": f"[Ringkasan respons sebelumnya: {summary}]",
                "_compacted": True,
                "_summary_boundary": True,
            }
            result.append(summary_msg)
            logger.info(
                f"Chat append-only compaction: appended summary turn, "
                f"preserved {len(messages)} historical turns byte-identical"
            )

        return result

    def _summarize_assistant(self, content: str) -> str:
        """Extract key information from assistant response for compact summary."""
        # Extract key conclusions, prices, recommendations
        lines = content.split("\n")
        key_lines = []
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            # Keep lines with prices, percentages, or key trading terms
            if re.search(
                r"\d+\.\d+|buy|sell|hold|bullish|bearish|support|resistance|"
                r"stop.?loss|take.?profit|ATR|RSI|trend|breakout|consolidat",
                line_stripped,
                re.IGNORECASE,
            ):
                key_lines.append(line_stripped)

        summary = " | ".join(key_lines[:5])
        if len(summary) > self.ASSISTANT_SUMMARY_MAX_CHARS:
            summary = summary[: self.ASSISTANT_SUMMARY_MAX_CHARS] + "..."
        return summary or (content[:200] + "...")
