# ==============================================================================
# File: gateway/omnichannel_streamer.py
# ==============================================================================

"""
Omnichannel Adaptive Stream Consumer with 3-Strikes Flood Fallback.
Provides resilient, high-fidelity real-time token streaming across messaging platforms
(Telegram, Discord, Slack) with automatic code fence closure, mid-stream bubble splitting,
and intelligent 429 flood control.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import Any, Callable, Coroutine, Optional, Tuple

logger = logging.getLogger("TradingAgent.Gateway.OmnichannelStreamer")

_CODE_FENCE_REGEX = re.compile(r"^```", re.MULTILINE)
_THINK_CLOSED_REGEX = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_REGEX = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)


def scrub_thinking_tokens(text: str) -> Tuple[str, str]:
    """
    Separates internal thinking tokens (<think>...</think>) from public conversational text.
    Returns (cleaned_text, thoughts).
    """
    if not text:
        return "", ""

    thoughts: list[str] = []
    for m in _THINK_CLOSED_REGEX.finditer(text):
        thoughts.append(m.group(1).strip())

    cleaned = _THINK_CLOSED_REGEX.sub("", text)
    unclosed_m = _THINK_OPEN_REGEX.search(cleaned)
    if unclosed_m:
        thoughts.append(unclosed_m.group(0).replace("<think>", "").strip())
        cleaned = _THINK_OPEN_REGEX.sub("", cleaned)

    return cleaned.strip(), "\n".join(thoughts).strip()


def balance_code_fences(text: str) -> str:
    """Balances unclosed markdown code blocks for partial streaming message previews."""
    if not text:
        return ""

    fence_matches = list(_CODE_FENCE_REGEX.finditer(text))
    if len(fence_matches) % 2 != 0:
        return text.rstrip() + "\n```"
    return text


class OmnichannelStreamer:
    """
    Adaptive live-stream consumer with:
    - 3-strikes flood rate-limit fallback (429 handling)
    - Mid-stream bubble overflow splitting (< 3850 chars)
    - Code-fence balancing & cursor handling
    - Prefix-stable progressive updates
    """

    def __init__(
        self,
        send_message_fn: Callable[[str], Coroutine[Any, Any, Any]],
        edit_message_fn: Optional[Callable[[Any, str], Coroutine[Any, Any, Any]]] = None,
        initial_interval: float = 1.0,
        max_interval: float = 4.0,
        max_chars_per_message: int = 3850,
        flood_threshold: int = 3,
        cursor: str = " ▌",
        scrub_thinking: bool = True,
    ):
        self.send_message_fn = send_message_fn
        self.edit_message_fn = edit_message_fn
        self.initial_interval = initial_interval
        self.max_interval = max_interval
        self.max_chars_per_message = max_chars_per_message
        self.flood_threshold = flood_threshold
        self.cursor = cursor
        self.scrub_thinking = scrub_thinking

        self._active_message: Optional[Any] = None
        self._current_bubble_text: str = ""
        self._total_accumulated_text: str = ""
        self._interval: float = initial_interval
        self._last_edit_time: float = 0.0
        self._consecutive_429: int = 0
        self._fallback_tail_only: bool = False
        self._lock = asyncio.Lock()

    @property
    def is_fallback_tail_only(self) -> bool:
        return self._fallback_tail_only

    async def _ensure_active_message(self, initial_text: str = "...") -> Any:
        if self._active_message is None:
            self._active_message = await self.send_message_fn(initial_text)
        return self._active_message

    async def feed_token(self, token: str) -> None:
        """Process an incoming token from the streaming generator."""
        if not token:
            return

        async with self._lock:
            self._total_accumulated_text += token
            self._current_bubble_text += token

            # Mid-stream overflow check
            if len(self._current_bubble_text) >= self.max_chars_per_message:
                await self._seal_current_bubble_and_split()
                return

            if self._fallback_tail_only:
                return

            now = time.monotonic()
            if (now - self._last_edit_time) >= self._interval and len(self._current_bubble_text) > 15:
                await self._apply_progressive_edit(now)

    async def _apply_progressive_edit(self, now: float) -> None:
        msg = await self._ensure_active_message()
        if not msg:
            return

        display_text = self._current_bubble_text
        if self.scrub_thinking:
            display_text, _ = scrub_thinking_tokens(display_text)

        if not display_text.strip():
            return

        balanced = balance_code_fences(display_text)
        payload = f"{balanced}{self.cursor}"

        try:
            if self.edit_message_fn:
                await self.edit_message_fn(msg, payload)
            elif hasattr(msg, "edit_text"):
                await msg.edit_text(payload)
            self._last_edit_time = now
            self._consecutive_429 = 0
            self._interval = max(self.initial_interval, self._interval * 0.95)
        except Exception as exc:
            err_str = str(exc).lower()
            if "retry" in err_str or "flood" in err_str or "429" in err_str:
                self._consecutive_429 += 1
                self._interval = min(self.max_interval, self._interval * 2.0)
                logger.warning(
                    f"[OmnichannelStreamer] 429 Flood hit ({self._consecutive_429}/{self.flood_threshold}). "
                    f"Backing off interval to {self._interval:.1f}s."
                )
                if self._consecutive_429 >= self.flood_threshold:
                    self._fallback_tail_only = True
                    logger.warning("[OmnichannelStreamer] 3-Strikes Flood tripped. Switched to tail-only mode.")
            else:
                logger.debug(f"[OmnichannelStreamer] Edit ignored: {exc}")

    async def _seal_current_bubble_and_split(self) -> None:
        """Seals the full message bubble and prepares a new bubble for subsequent tokens."""
        if self._active_message:
            final_bubble = self._current_bubble_text
            if self.scrub_thinking:
                final_bubble, _ = scrub_thinking_tokens(final_bubble)
            final_bubble = balance_code_fences(final_bubble)

            try:
                if self.edit_message_fn:
                    await self.edit_message_fn(self._active_message, final_bubble)
                elif hasattr(self._active_message, "edit_text"):
                    await self._active_message.edit_text(final_bubble)
            except Exception as e:
                logger.debug(f"[OmnichannelStreamer] Seal edit failed: {e}")

        # Check if we were inside an open code block when splitting
        open_fence_prefix = ""
        fence_matches = list(_CODE_FENCE_REGEX.finditer(self._current_bubble_text))
        if len(fence_matches) % 2 != 0:
            last_match = list(re.finditer(r"```(\w*)", self._current_bubble_text))[-1]
            lang = last_match.group(1) or ""
            open_fence_prefix = f"```{lang}\n"

        # Spawn new bubble
        self._current_bubble_text = open_fence_prefix
        self._active_message = await self.send_message_fn(self._current_bubble_text or "...")
        self._last_edit_time = time.monotonic()

    async def finish(self) -> str:
        """Finalizes streaming, removes cursor, and commits clean text to message."""
        async with self._lock:
            final_text = self._current_bubble_text
            if self.scrub_thinking:
                final_text, _ = scrub_thinking_tokens(final_text)

            final_text = balance_code_fences(final_text)
            if not final_text.strip():
                final_text = "[PERINGATAN] Tidak ada respons yang dihasilkan."

            if self._active_message is None:
                self._active_message = await self.send_message_fn(final_text)
            else:
                try:
                    if self.edit_message_fn:
                        await self.edit_message_fn(self._active_message, final_text)
                    elif hasattr(self._active_message, "edit_text"):
                        await self._active_message.edit_text(final_text)
                except Exception as e:
                    logger.debug(f"[OmnichannelStreamer] Final edit error: {e}")

            return self._total_accumulated_text
