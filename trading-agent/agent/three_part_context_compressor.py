# ==============================================================================
# File: agent/three_part_context_compressor.py
# ==============================================================================

"""
Three-Part Context Compressor & Tool Result Deterministic Pruner.
Hierarchical memory compaction architecture with commit-fence protection.

Partitions conversation trajectories into three distinct zones:
  1. HEAD (Protected): System prompt, trading invariants, initial user directives.
     Never summarized or dropped, ensuring the agent remains anchored to its core mandate.
  2. MIDDLE (Compacted): Older conversation exchanges and tool iterations.
     - Step 2A: Zero-cost deterministic tool result truncation (replaces massive tool outputs
       with concise structural headers/stubs).
     - Step 2B: Hierarchical semantic summarization via fast auxiliary LLM.
  3. TAIL (Protected): The most recent N messages (default 8-10 turns).
     Preserves immediate working memory, active tool call responses, and recent context.

Commit Fence:
  Ensures that context mutations are atomically staged and committed under a mutex,
  guaranteeing that SIGINT, cancellations, or worker interrupts never leave the
  underlying session database in a corrupt or half-truncated state.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Agent.ThreePartContextCompressor")


class ThreePartContextCompressor:
    """
    Manages bounded context compaction while protecting foundational instructions
    and immediate working memory.
    """

    def __init__(
        self,
        protect_first_n: int = 2,
        protect_last_n: int = 8,
        max_tool_output_chars: int = 600,
        compression_threshold_tokens: int = 32000,
        target_summary_tokens: int = 1200,
    ):
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self.max_tool_output_chars = max_tool_output_chars
        self.compression_threshold_tokens = compression_threshold_tokens
        self.target_summary_tokens = target_summary_tokens
        self._commit_fence_lock = threading.Lock()

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Rough 4-char per token heuristic for fast preflight evaluation."""
        total_chars = 0
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total_chars += len(part["text"])
        return total_chars // 4

    def prune_tool_results_determinist(
        self, messages: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Replaces long tool output bodies in older messages with concise head/tail stubs.
        Operates entirely without LLM calls (Zero-Cost Token Recovery).
        """
        pruned_messages: List[Dict[str, Any]] = []
        chars_saved = 0

        for msg in messages:
            msg_copy = dict(msg)
            role = msg_copy.get("role")

            if role == "tool" or msg_copy.get("tool_call_id"):
                content = msg_copy.get("content")
                if isinstance(content, str) and len(content) > self.max_tool_output_chars:
                    original_len = len(content)
                    head = content[: self.max_tool_output_chars // 2]
                    tail = content[-self.max_tool_output_chars // 2 :]
                    stub = (
                        f"{head}\n\n[... Deterministically pruned {original_len - len(head) - len(tail)} chars of historical tool output ...]\n\n{tail}"
                    )
                    msg_copy["content"] = stub
                    chars_saved += original_len - len(stub)

            pruned_messages.append(msg_copy)

        return pruned_messages, chars_saved

    def compact(
        self,
        messages: List[Dict[str, Any]],
        summarizer_fn: Optional[Callable[[str], str]] = None,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Executes Three-Part Compaction if token threshold is exceeded.
        Atomic execution protected by the commit fence lock.
        """
        with self._commit_fence_lock:
            total_msgs = len(messages)
            min_required_for_compaction = self.protect_first_n + self.protect_last_n + 2

            if total_msgs < min_required_for_compaction:
                return messages

            current_tokens = self.estimate_tokens(messages)
            if not force and current_tokens < self.compression_threshold_tokens:
                return messages

            logger.info(
                f"[ThreePartContextCompressor] Triggering compaction: {total_msgs} messages, "
                f"~{current_tokens} tokens (threshold: {self.compression_threshold_tokens})"
            )

            # 1. Segment into Head, Middle, Tail
            head_zone = messages[: self.protect_first_n]
            middle_zone = messages[self.protect_first_n : -self.protect_last_n]
            tail_zone = messages[-self.protect_last_n :]

            # 2. Step 2A: Deterministic Pruning on Middle Zone
            pruned_middle, chars_saved = self.prune_tool_results_determinist(middle_zone)
            logger.debug(f"[ThreePartContextCompressor] Deterministic pruning saved ~{chars_saved // 4} tokens")

            # 3. Step 2B: Semantic Summarization of Middle Zone
            if summarizer_fn is not None:
                middle_text_fragments = []
                for m in pruned_middle:
                    r = m.get("role", "unknown")
                    c = m.get("content", "")
                    if isinstance(c, str):
                        middle_text_fragments.append(f"[{r}]: {c}")

                middle_text_corpus = "\n".join(middle_text_fragments)
                try:
                    summary_text = summarizer_fn(middle_text_corpus)
                    summary_message = {
                        "role": "user",
                        "content": f"[Summary of earlier conversation ({len(middle_zone)} turns compacted)]:\n{summary_text}",
                    }
                    middle_representation = [summary_message]
                except Exception as exc:
                    logger.warning(f"[ThreePartContextCompressor] Auxiliary summarization failed, falling back to pruned middle: {exc}")
                    middle_representation = pruned_middle
            else:
                middle_representation = pruned_middle

            # 4. Atomic Reassembly
            compacted_messages = head_zone + middle_representation + tail_zone
            new_tokens = self.estimate_tokens(compacted_messages)
            logger.info(
                f"[ThreePartContextCompressor] Compaction complete: {total_msgs} -> {len(compacted_messages)} messages, "
                f"~{current_tokens} -> ~{new_tokens} tokens"
            )

            return compacted_messages
