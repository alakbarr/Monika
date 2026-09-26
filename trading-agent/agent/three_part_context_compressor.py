# ==============================================================================
# File: agent/three_part_context_compressor.py
# ==============================================================================

"""
Three-Part Context Compressor & Dual-Tier Compaction Engine.
Hierarchical memory compaction architecture with commit-fence protection and rolling micro-compaction.

Partitions conversation trajectories into three distinct zones:
  1. HEAD (Protected): System prompt, trading invariants, initial user directives.
     Never summarized or dropped, ensuring the agent remains anchored to its core mandate.
  2. MIDDLE (Compacted): Older conversation exchanges and tool iterations.
     - Step 2A: Zero-cost deterministic tool result truncation (replaces massive tool outputs
       with concise structural headers/stubs).
     - Step 2B: Hierarchical semantic summarization with role-alternation preservation.
  3. TAIL (Protected): The most recent N messages (default 8-10 turns).
     Preserves immediate working memory, active tool call responses, and recent context.

Rolling Micro-Compactor:
  Continuously compresses individual historical tool-assistant exchanges between turns
  without touching user directives, keeping working memory lean.
"""

from __future__ import annotations

import inspect
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("TradingAgent.Agent.ThreePartContextCompressor")


class ThreePartContextCompressor:
    """
    Manages bounded context compaction while protecting foundational instructions,
    immediate working memory, and valid role alternations.
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

    def micro_compact_exchange(
        self,
        messages: List[Dict[str, Any]],
        exchange_summarizer: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scans messages for completed historical assistant+tool exchanges and compacts
        them into a concise assistant memory note, NEVER compressing user instructions.
        """
        if len(messages) <= self.protect_last_n + 2:
            return messages

        compacted: List[Dict[str, Any]] = []
        i = 0
        limit = len(messages) - self.protect_last_n

        def safe_append(target_list: List[Dict[str, Any]], msg: Dict[str, Any]) -> None:
            if not target_list:
                target_list.append(dict(msg))
                return
            prev = target_list[-1]
            if prev.get("role") == msg.get("role") and msg.get("role") in ("user", "assistant"):
                prev_content = prev.get("content") or ""
                new_content = msg.get("content") or ""
                prev["content"] = f"{prev_content}\n\n{new_content}".strip()
                if msg.get("tool_calls"):
                    prev["tool_calls"] = (prev.get("tool_calls") or []) + msg["tool_calls"]
            else:
                target_list.append(dict(msg))

        while i < len(messages):
            # If within head or tail zone, keep as is
            if i < self.protect_first_n or i >= limit:
                safe_append(compacted, messages[i])
                i += 1
                continue

            msg = messages[i]
            # Look for assistant tool calling block followed by tool responses
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_exchange = [msg]
                j = i + 1
                while j < limit and messages[j].get("role") in ("tool", "assistant"):
                    tool_exchange.append(messages[j])
                    j += 1

                # If exchange has tool calls + responses and summarizer is provided
                if len(tool_exchange) >= 2 and exchange_summarizer:
                    exchange_text = "\n".join(f"[{m.get('role')}]: {m.get('content') or ''}" for m in tool_exchange)
                    try:
                        summary = exchange_summarizer(exchange_text)
                        safe_append(compacted, {
                            "role": "assistant",
                            "content": f"[Historical Tool Execution Summary]: {summary}",
                        })
                        i = j
                        continue
                    except Exception as e:
                        logger.debug(f"[ThreePartContextCompressor] Micro-compact failed: {e}")

            safe_append(compacted, messages[i])
            i += 1

        return compacted

    def compact(
        self,
        messages: List[Dict[str, Any]],
        summarizer_fn: Optional[Callable[[str], str]] = None,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Executes Three-Part Macro Compaction if token threshold is exceeded.
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
                    # Preserve valid role alternation: if head ends with user, summary is assistant
                    head_last_role = head_zone[-1].get("role") if head_zone else "system"
                    summary_role = "assistant" if head_last_role == "user" else "user"
                    summary_message = {
                        "role": summary_role,
                        "content": f"[Summary of earlier conversation ({len(middle_zone)} turns compacted)]:\n{summary_text}",
                    }
                    middle_representation = [summary_message]
                except Exception as exc:
                    logger.warning(f"[ThreePartContextCompressor] Auxiliary summarization failed, falling back to pruned middle: {exc}")
                    middle_representation = pruned_middle
            else:
                middle_representation = pruned_middle

            # 4. Atomic Reassembly & Alternation Verification
            compacted_messages = head_zone + middle_representation + tail_zone
            new_tokens = self.estimate_tokens(compacted_messages)
            logger.info(
                f"[ThreePartContextCompressor] Compaction complete: {total_msgs} -> {len(compacted_messages)} messages, "
                f"~{current_tokens} -> ~{new_tokens} tokens"
            )

            return compacted_messages
