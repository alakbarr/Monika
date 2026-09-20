"""
File: trading-agent/utils/streaming/stream_scrubber.py

Stateful Stream Scrubber Pipeline.
Buffers and scrubs reasoning tokens (<think>...</think>), internal context tags,
and sensitive credentials across streaming delta boundaries before dispatch to
Telegram, WebSocket UI, or logs.
"""

import re
from typing import List, Optional, Set

SECRET_PATTERNS = [
    (re.compile(r"(?:api[_-]?key|token|secret|password|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{12,})['\"]?", re.IGNORECASE), "[REDACTED_SECRET]"),
    (re.compile(r"bot\d{8,12}:[A-Za-z0-9_-]{35,}", re.IGNORECASE), "[REDACTED_TELEGRAM_TOKEN]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
]

STRIP_TAG_PAIRS = [
    ("think", "think"),
    ("thought", "thought"),
    ("memory-context", "memory-context"),
    ("market-memory-context", "market-memory-context"),
    ("untrusted_external_content", "untrusted_external_content"),
    ("volatile_overlay", "volatile_overlay"),
]


class StatefulStreamScrubber:
    """
    Stateful streaming text scrubber with boundary buffering.
    Safely eliminates reasoning blocks and internal metadata across partial stream chunks.
    """

    def __init__(
        self,
        strip_thinking: bool = True,
        strip_internal_tags: bool = True,
        redact_secrets: bool = True,
    ):
        self.strip_thinking = strip_thinking
        self.strip_internal_tags = strip_internal_tags
        self.redact_secrets = redact_secrets

        self._buffer: str = ""
        self._in_think: bool = False
        self._in_internal_tag: Optional[str] = None
        self._accumulated_thinking: List[str] = []

        # Build set of monitored tags
        self._target_tags: Set[str] = set()
        if self.strip_thinking:
            self._target_tags.update(["think", "thought"])
        if self.strip_internal_tags:
            self._target_tags.update([
                "memory-context", "market-memory-context",
                "untrusted_external_content", "volatile_overlay"
            ])

    @property
    def accumulated_thinking(self) -> str:
        """Full reasoning trace extracted from stream, suitable for DB trace storage."""
        return "".join(self._accumulated_thinking).strip()

    def process_delta(self, delta: str) -> str:
        """
        Ingest a streaming delta and return sanitized visible text.
        Buffers incomplete tags at chunk boundaries.
        """
        if not delta:
            return ""

        self._buffer += delta
        output_chunks: List[str] = []

        while self._buffer:
            if self._in_think:
                # Look for closing </think> or </thought>
                close_match = re.search(r"</\s*(?:think|thought)\s*>", self._buffer, re.IGNORECASE)
                if close_match:
                    # Capture thinking content before close
                    self._accumulated_thinking.append(self._buffer[:close_match.start()])
                    self._buffer = self._buffer[close_match.end():]
                    self._in_think = False
                else:
                    # Still inside thinking block; save thinking and check boundary
                    if "</" in self._buffer:
                        idx = self._buffer.rfind("</")
                        self._accumulated_thinking.append(self._buffer[:idx])
                        self._buffer = self._buffer[idx:]
                    else:
                        self._accumulated_thinking.append(self._buffer)
                        self._buffer = ""
                    break

            elif self._in_internal_tag:
                # Look for closing internal tag
                tag_name = re.escape(self._in_internal_tag)
                close_match = re.search(rf"</\s*{tag_name}\s*>", self._buffer, re.IGNORECASE)
                if close_match:
                    self._buffer = self._buffer[close_match.end():]
                    self._in_internal_tag = None
                else:
                    if "</" in self._buffer:
                        idx = self._buffer.rfind("</")
                        self._buffer = self._buffer[idx:]
                    else:
                        self._buffer = ""
                    break

            else:
                # Outside any strip block: scan for opening tags
                match = re.search(r"<\s*([a-zA-Z0-9_\-]+)\b[^>]*>", self._buffer)
                if match:
                    tag_candidate = match.group(1).lower()
                    if tag_candidate in self._target_tags:
                        # Emit text prior to tag
                        prior_text = self._buffer[:match.start()]
                        if prior_text:
                            output_chunks.append(prior_text)

                        self._buffer = self._buffer[match.end():]
                        if tag_candidate in ("think", "thought"):
                            self._in_think = True
                        else:
                            self._in_internal_tag = tag_candidate
                        continue
                    else:
                        # Legitimate tag (or HTML/markdown), emit up to tag end
                        output_chunks.append(self._buffer[:match.end()])
                        self._buffer = self._buffer[match.end():]
                        continue
                else:
                    # No complete opening tag found. Check if trailing text contains an incomplete '<'
                    if "<" in self._buffer:
                        last_lt = self._buffer.rfind("<")
                        # If the '<' is near end of buffer (< 50 chars), retain for next delta
                        if len(self._buffer) - last_lt < 50:
                            output_chunks.append(self._buffer[:last_lt])
                            self._buffer = self._buffer[last_lt:]
                            break
                    # No potential tag prefix, flush entire buffer
                    output_chunks.append(self._buffer)
                    self._buffer = ""
                    break

        emitted = "".join(output_chunks)
        if self.redact_secrets and emitted:
            emitted = self._apply_redactions(emitted)
        return emitted

    def flush(self) -> str:
        """
        Flush any remaining buffered text when stream finishes.
        """
        remaining = self._buffer
        self._buffer = ""
        if self._in_think or self._in_internal_tag:
            return ""
        if self.redact_secrets and remaining:
            remaining = self._apply_redactions(remaining)
        return remaining

    def _apply_redactions(self, text: str) -> str:
        res = text
        for pattern, replacement in SECRET_PATTERNS:
            res = pattern.sub(replacement, res)
        return res

    @classmethod
    def scrub_text(
        cls,
        text: str,
        strip_thinking: bool = True,
        strip_internal_tags: bool = True,
        redact_secrets: bool = True,
    ) -> str:
        """Convenience method to scrub a complete text string in one pass."""
        if not text:
            return ""
        scrubber = cls(
            strip_thinking=strip_thinking,
            strip_internal_tags=strip_internal_tags,
            redact_secrets=redact_secrets,
        )
        emitted = scrubber.process_delta(text)
        flushed = scrubber.flush()
        return (emitted + flushed).strip()

