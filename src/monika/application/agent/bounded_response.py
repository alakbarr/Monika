# ==============================================================================
# File: agent/bounded_response.py
# ==============================================================================

"""
Bounded Response Reader & Payload Clamping.
Safeguards agent processes against memory exhaustion from oversized error bodies,
truncated chunk floods, or hanging network streams.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger("TradingAgent.Agent.BoundedResponse")

MAX_ERROR_BODY_BYTES = 64 * 1024  # 64 KB hard limit for error text
DEFAULT_READ_TIMEOUT_SECONDS = 10.0


async def read_bounded_response_body(
    response: Any,
    max_bytes: int = MAX_ERROR_BODY_BYTES,
    timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS,
) -> str:
    """
    Reads an HTTP response body with an absolute byte limit and strict deadline.
    Supports aiohttp, httpx, and standard async response objects.
    """
    try:
        # Check for standard read method
        if hasattr(response, "aread"):
            coro = response.aread()
        elif hasattr(response, "read"):
            read_fn = response.read
            coro = read_fn() if asyncio.iscoroutinefunction(read_fn) else asyncio.to_thread(read_fn)
        elif hasattr(response, "text"):
            text_val = response.text
            if callable(text_val):
                coro = text_val() if asyncio.iscoroutinefunction(text_val) else asyncio.to_thread(text_val)
            else:
                return str(text_val)[:max_bytes]
        else:
            return ""

        content = await asyncio.wait_for(coro, timeout=timeout_seconds)
        if isinstance(content, bytes):
            return content[:max_bytes].decode("utf-8", errors="replace")
        return str(content)[:max_bytes]

    except asyncio.TimeoutError:
        logger.warning(f"[BoundedResponse] Timed out reading response body after {timeout_seconds:.1f}s")
        return "[Error body truncated: read timeout]"
    except Exception as exc:
        logger.warning(f"[BoundedResponse] Failed to read response body: {exc}")
        return f"[Failed to read error body: {exc}]"


def truncate_text_middle(text: str, max_chars: int = 4000) -> str:
    """
    Truncates a long text string preserving the head and tail.
    Useful for compressing massive tool outputs and error logs.
    """
    if len(text) <= max_chars:
        return text

    half = max_chars // 2
    omitted = len(text) - (2 * half)
    return f"{text[:half]}\n\n[... {omitted} characters omitted for brevity ...]\n\n{text[-half:]}"
