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
from typing import List, Tuple

logger = logging.getLogger("TradingAgent.Providers.StreamingThinkScrubber")


class StreamingThinkScrubber:
    """
    State machine that processes streaming text chunks and separates
    internal reasoning from final public response tokens.
    """

    def __init__(self):
        self._in_think_block = False
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
                # Look for opening tag <think>
                idx = self._buffer.find("<think>")
                if idx != -1:
                    # Content before <think>
                    before = self._buffer[:idx]
                    if before:
                        content_out.append(before)
                    self._in_think_block = True
                    self._buffer = self._buffer[idx + 7:]  # len('<think>') == 7
                else:
                    # Check for partial prefix of '<think>' at the end of buffer
                    partial_found = False
                    for p_len in range(1, 7):
                        if "<think>".startswith(self._buffer[-p_len:]):
                            safe_content = self._buffer[:-p_len]
                            if safe_content:
                                content_out.append(safe_content)
                            self._buffer = self._buffer[-p_len:]
                            partial_found = True
                            break
                    if not partial_found:
                        content_out.append(self._buffer)
                        self._buffer = ""
                    else:
                        break

            else:
                # Inside think block, look for closing tag </think>
                idx = self._buffer.find("</think>")
                if idx != -1:
                    thought = self._buffer[:idx]
                    if thought:
                        thinking_out.append(thought)
                    self._in_think_block = False
                    self._buffer = self._buffer[idx + 8:]  # len('</think>') == 8
                else:
                    # Check for partial prefix of '</think>' at the end of buffer
                    partial_found = False
                    for p_len in range(1, 8):
                        if "</think>".startswith(self._buffer[-p_len:]):
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

    @property
    def total_content(self) -> str:
        return "".join(self._accumulated_content)

    @property
    def total_thinking(self) -> str:
        return "".join(self._accumulated_thinking)
