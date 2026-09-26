# ==============================================================================
# File: gateway/stream_consumer.py
# ==============================================================================

"""
Omni-Channel Streaming Consumer with Code Fence Balancing & Rate-Limit Throttling.
Institutional-grade gateway and multi-channel architecture.

Consumes real-time streaming tokens, buffers them with debounced rate-limiting,
and guarantees that open markdown code fences (```) are safely closed during intermediate
message updates, preventing visual syntax corruption on chat clients (Telegram, Discord, Slack).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger("TradingAgent.Gateway.StreamConsumer")

_CODE_FENCE_REGEX = re.compile(r"^```", re.MULTILINE)


def ensure_closed_code_fences(text: str) -> str:
    """
    Balances unclosed markdown code blocks for partial streaming message previews.
    If an unclosed code block is detected, appends a temporary closing fence.
    """
    if not text:
        return ""

    fence_matches = list(_CODE_FENCE_REGEX.finditer(text))
    fence_count = len(fence_matches)

    # Odd count means an open code block has not been closed yet
    if fence_count % 2 != 0:
        return text.rstrip() + "\n```"

    return text


class LiveStreamConsumer:
    """
    Throttled streaming accumulator for platform message dispatching.
    Flushes partial text updates to a destination callback at controlled intervals.
    """

    def __init__(
        self,
        flush_interval_seconds: float = 0.5,
        publisher_callback: Optional[Callable[[str, bool], Coroutine[Any, Any, None]]] = None,
    ):
        self.flush_interval_seconds = flush_interval_seconds
        self.publisher_callback = publisher_callback
        self._buffer: str = ""
        self._last_flush_time: float = 0.0
        self._is_completed: bool = False
        self._lock = asyncio.Lock()

    async def feed_token(self, token: str) -> None:
        """Feed a new streaming token into the accumulator."""
        async with self._lock:
            self._buffer += token
            now = time.time()
            if (now - self._last_flush_time) >= self.flush_interval_seconds:
                await self._flush_internal(is_final=False)
                self._last_flush_time = now

    async def _flush_internal(self, is_final: bool = False) -> None:
        if not self.publisher_callback or not self._buffer:
            return

        # Prepare balanced content
        if not is_final:
            display_text = ensure_closed_code_fences(self._buffer)
        else:
            display_text = self._buffer

        try:
            await self.publisher_callback(display_text, is_final)
        except Exception as e:
            logger.warning(f"[LiveStreamConsumer] Failed to publish stream update: {e}")

    async def finish(self) -> str:
        """Signal end of stream and perform final flush."""
        async with self._lock:
            self._is_completed = True
            await self._flush_internal(is_final=True)
            return self._buffer

    @property
    def accumulated_text(self) -> str:
        return self._buffer
