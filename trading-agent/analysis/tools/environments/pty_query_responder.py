# ==============================================================================
# File: analysis/tools/environments/pty_query_responder.py
# ==============================================================================

"""
PTY Escape Query Responder & Terminal Protocol Synthesizer.
Institutional-grade execution sandbox architecture.

Automatically detects and synthesizes immediate responses to VT100 / xterm
ANSI terminal query sequences (e.g. Device Attributes, Cursor Position, Window Size)
emitted by interactive terminal subprocesses (git, less, vim, fzf, npm).
Prevents subprocess deadlocks where an interactive CLI process hangs indefinitely
waiting for terminal handshake responses on stdin.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple, Union

logger = logging.getLogger("TradingAgent.Tools.PtyQueryResponder")

# Compiled regex patterns for common terminal inquiry sequences
_QUERY_PATTERNS = [
    # Cursor Position Report query: ESC [ 6 n
    (re.compile(rb"\x1b\[6n"), b"\x1b[1;1R", "Cursor Position Report"),
    # Primary Device Attributes query: ESC [ c or ESC [ 0 c
    (re.compile(rb"\x1b\[0?c"), b"\x1b[?1;2c", "Primary Device Attributes"),
    # Secondary Device Attributes query: ESC [ > c or ESC [ > 0 c
    (re.compile(rb"\x1b\[>0?c"), b"\x1b[>0;10;0c", "Secondary Device Attributes"),
    # Window Size report query: ESC [ 18 t
    (re.compile(rb"\x1b\[18t"), b"\x1b[8;24;80t", "Window Size (24x80)"),
    # Foreground color inquiry: ESC ] 10 ; ? BEL or ST
    (re.compile(rb"\x1b\]10;\?(?:\x07|\x1b\\)"), b"\x1b]10;rgb:ffff/ffff/ffff\x07", "Foreground Color Inquiry"),
    # Background color inquiry: ESC ] 11 ; ? BEL or ST
    (re.compile(rb"\x1b\]11;\?(?:\x07|\x1b\\)"), b"\x1b]11;rgb:0000/0000/0000\x07", "Background Color Inquiry"),
]


class PtyQueryResponder:
    """
    Stream filter and automatic responder for ANSI/VT terminal interrogation queries.
    """

    def __init__(self):
        self._residual_buffer = bytearray()

    def process_output(self, data: Union[bytes, str]) -> List[bytes]:
        """
        Inspects output bytes from subprocess stdout/pty.
        Returns a list of synthetic response byte sequences to immediately write into stdin.
        """
        if isinstance(data, str):
            data_bytes = data.encode("utf-8", errors="replace")
        else:
            data_bytes = data

        responses: List[bytes] = []
        if not data_bytes:
            return responses

        # Append to buffer to handle queries split across chunk boundaries
        self._residual_buffer.extend(data_bytes)
        buf = bytes(self._residual_buffer)

        # Check for query escape sequences and consume matched ranges
        matched_spans: List[Tuple[int, int]] = []
        for pattern, response, desc in _QUERY_PATTERNS:
            for match in pattern.finditer(buf):
                logger.debug(f"[PtyQueryResponder] Detected {desc} in terminal stream -> responding: {response!r}")
                responses.append(response)
                matched_spans.append(match.span())

        if matched_spans:
            # Remove all matched query sequences from buffer
            matched_spans.sort(key=lambda s: s[0])
            new_buf = bytearray()
            idx = 0
            for start, end in matched_spans:
                if start > idx:
                    new_buf.extend(self._residual_buffer[idx:start])
                idx = max(idx, end)
            if idx < len(self._residual_buffer):
                new_buf.extend(self._residual_buffer[idx:])
            self._residual_buffer = new_buf

        # Keep only the tail of buffer if it ends with partial ESC sequence (< 16 bytes)
        last_esc = self._residual_buffer.rfind(b"\x1b")
        if last_esc != -1 and (len(self._residual_buffer) - last_esc) < 16:
            self._residual_buffer = self._residual_buffer[last_esc:]
        else:
            self._residual_buffer.clear()

        return responses

    def filter_and_respond(self, data: bytes) -> Tuple[bytes, List[bytes]]:
        """
        Processes stream output, returning (clean_data, stdin_responses).
        """
        responses = self.process_output(data)
        return data, responses
