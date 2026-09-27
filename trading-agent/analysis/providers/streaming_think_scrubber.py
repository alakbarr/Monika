# ==============================================================================
# File: analysis/providers/streaming_think_scrubber.py
# ==============================================================================

"""
Real-Time Streaming Think Tag Scrubber.
Institutional-grade LLM provider orchestration architecture.

Processes incremental SSE token chunks from reasoning models (DeepSeek, Qwen, etc.),
extracting thought processes (<think>...</think>) into a separate stream while
emitting only clean, scrubbed response tokens to end users without tag leakage.
Handles partial boundary tags split across consecutive streaming chunks.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Providers.StreamingThinkScrubber")


DEFAULT_REASONING_TAG_PAIRS: List[Tuple[str, str]] = [
    ("<think>", "</think>"),
    ("<thought>", "</thought>"),
    ("<reasoning>", "</reasoning>"),
    ("<scratchpad>", "</scratchpad>"),
]


class StreamingThinkScrubber:
    """
    State machine that processes streaming text chunks and separates
    internal reasoning from final public response tokens across all supported tag pairs.
    """

    def __init__(self, tag_pairs: Optional[List[Tuple[str, str]]] = None):
        self.tag_pairs = tag_pairs or list(DEFAULT_REASONING_TAG_PAIRS)
        self._in_think_block = False
        self._active_closing_tag: str = "</think>"
        self._buffer = ""
        self._accumulated_thinking: List[str] = []
        self._accumulated_content: List[str] = []

    def feed_chunk(self, chunk: str) -> Tuple[str, str]:
        """
        Feeds an incoming stream chunk.
        Returns a tuple: (content_delta: str, thinking_delta: str).
        """
        if not chunk:
            return "", ""

        self._buffer += chunk
        content_out: List[str] = []
        thinking_out: List[str] = []

        while self._buffer:
            if not self._in_think_block:
                # Look for earliest opening tag among all registered tag pairs
                earliest_idx = -1
                found_open = ""
                found_close = ""

                for open_tag, close_tag in self.tag_pairs:
                    idx = self._buffer.find(open_tag)
                    if idx != -1 and (earliest_idx == -1 or idx < earliest_idx):
                        earliest_idx = idx
                        found_open = open_tag
                        found_close = close_tag

                if earliest_idx != -1:
                    before = self._buffer[:earliest_idx]
                    if before:
                        content_out.append(before)
                    self._in_think_block = True
                    self._active_closing_tag = found_close
                    self._buffer = self._buffer[earliest_idx + len(found_open):]
                else:
                    # Check for partial prefix of any opening tag at buffer end
                    partial_found = False
                    for open_tag, _ in self.tag_pairs:
                        for p_len in range(1, len(open_tag)):
                            if open_tag.startswith(self._buffer[-p_len:]):
                                safe_content = self._buffer[:-p_len]
                                if safe_content:
                                    content_out.append(safe_content)
                                self._buffer = self._buffer[-p_len:]
                                partial_found = True
                                break
                        if partial_found:
                            break

                    if not partial_found:
                        content_out.append(self._buffer)
                        self._buffer = ""
                    else:
                        break

            else:
                # Inside think block, look for active closing tag
                idx = self._buffer.find(self._active_closing_tag)
                if idx != -1:
                    thought = self._buffer[:idx]
                    if thought:
                        thinking_out.append(thought)
                    self._in_think_block = False
                    self._buffer = self._buffer[idx + len(self._active_closing_tag):]
                else:
                    # Check for partial prefix of active closing tag at buffer end
                    partial_found = False
                    for p_len in range(1, len(self._active_closing_tag)):
                        if self._active_closing_tag.startswith(self._buffer[-p_len:]):
                            safe_thought = self._buffer[:-p_len]
                            if safe_thought:
                                thinking_out.append(safe_thought)
                            self._buffer = self._buffer[-p_len:]
                            partial_found = True
                            break

                    if not partial_found:
                        thinking_out.append(self._buffer)
                        self._buffer = ""
                    else:
                        break

        c_delta = "".join(content_out)
        t_delta = "".join(thinking_out)

        if c_delta:
            self._accumulated_content.append(c_delta)
        if t_delta:
            self._accumulated_thinking.append(t_delta)

        return c_delta, t_delta

    def finalize(self) -> Tuple[str, str]:
        """
        Flushes any remaining buffered text when stream ends.
        Returns (final_content_delta, final_thinking_delta).
        """
        c_delta = ""
        t_delta = ""
        if self._buffer:
            if self._in_think_block:
                t_delta = self._buffer
                self._accumulated_thinking.append(t_delta)
            else:
                c_delta = self._buffer
                self._accumulated_content.append(c_delta)
            self._buffer = ""

        return c_delta, t_delta

    @classmethod
    def scrub_text(cls, text: str) -> Tuple[str, str]:
        """One-shot utility to scrub reasoning tags from a complete text payload."""
        scrubber = cls()
        c1, t1 = scrubber.feed_chunk(text)
        c2, t2 = scrubber.finalize()
        return (c1 + c2).strip(), (t1 + t2).strip()

    @property
    def total_content(self) -> str:
        return "".join(self._accumulated_content)

    @property
    def total_thinking(self) -> str:
        return "".join(self._accumulated_thinking)

