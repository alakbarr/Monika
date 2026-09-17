"""
Micro-Compaction for Telegram Chat Sessions.

Key invariant: User messages are NEVER summarized (prevents goal drift).
Only assistant responses are compressed into summary markers.
"""
import logging
import json
import re
from typing import List, Dict, Any, Optional
from utils.llm.prompt_compressor import estimate_tokens, truncate_to_budget

logger = logging.getLogger("TradingAgent.ChatCompaction")


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
        compacted_count = 0

        # Walk from oldest to newest, compact assistant messages only
        for i in range(len(result)):
            if total_tokens <= threshold:
                break

            msg = result[i]
            if msg.get("role") != "assistant":
                continue  # NEVER compact user messages
            if msg.get("_compacted"):
                continue  # Already compacted

            original_content = str(msg.get("content", ""))
            original_tokens = estimate_tokens(original_content)

            if original_tokens <= 50:
                continue  # Too short to compress meaningfully

            # Compress: extract key info, then summarize
            summary = self._summarize_assistant(original_content)
            result[i] = {
                **msg,
                "role": "assistant",
                "content": f"[Ringkasan respons sebelumnya: {summary}]",
                "_compacted": True,
            }

            saved_tokens = original_tokens - estimate_tokens(summary)
            total_tokens -= saved_tokens
            compacted_count += 1

        if compacted_count > 0:
            logger.info(
                f"Chat micro-compaction: compacted {compacted_count} assistant turns, "
                f"history now ~{total_tokens} tokens"
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
                line_stripped, re.IGNORECASE
            ):
                key_lines.append(line_stripped)

        summary = " | ".join(key_lines[:5])
        if len(summary) > self.ASSISTANT_SUMMARY_MAX_CHARS:
            summary = summary[:self.ASSISTANT_SUMMARY_MAX_CHARS] + "..."
        return summary or (content[:200] + "...")
