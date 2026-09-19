# ==============================================================================
# File: utils/api/streaming.py
# ==============================================================================

"""
Universal async streaming consumer with idle-timeout liveness detection.

Mendukung 3 format streaming:
1. SSE (Server-Sent Events): data: {json}\n\n  — Gemini, OpenAI, Groq, OpenRouter
2. Typed SSE: event: <type>\ndata: {json}\n\n  — Anthropic
3. NDJSON: {json}\n  — Ollama native

Fitur:
- idle_timeout: Timeout jika tidak ada chunk baru dalam N detik
- safety_timeout: Timeout absolut (safety net jika chunk terus datang tanpa henti)
- first_chunk_timeout: Timeout khusus untuk chunk pertama (TTFT / reasoning time)
- Otomatis filter SSE comment lines (: OPENROUTER PROCESSING)
"""

import asyncio
import json
import time
import logging
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

import aiohttp

logger = logging.getLogger("TradingAgent.Streaming")


class StreamTimeoutError(Exception):
    """Raised when streaming idle timeout exceeded (no chunks received)."""
    def __init__(self, message: str, idle_seconds: float = 0.0,
                 chunks_received: int = 0, partial_text: str = ""):
        super().__init__(message)
        self.idle_seconds = idle_seconds
        self.chunks_received = chunks_received
        self.partial_text = partial_text


class StreamSafetyTimeoutError(StreamTimeoutError):
    """Raised when absolute safety timeout exceeded despite chunks still arriving."""
    pass


@dataclass
class StreamConfig:
    """Konfigurasi streaming timeout."""
    idle_timeout: float = 45.0          # Timeout jika tidak ada chunk baru
    safety_timeout: float = 600.0       # Safety net absolut
    first_chunk_timeout: float = 90.0    # Timeout menunggu chunk pertama


@dataclass
class StreamResult:
    """Hasil akumulasi dari streaming response."""
    text: str = ""
    thinking_text: str = ""
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""
    raw_chunks: list = field(default_factory=list)
    chunks_received: int = 0
    total_duration: float = 0.0


class StreamWriterFence:
    """Ensures only the latest retry's stream writes to output.

    When a stream retry occurs, an older stream may still emit delayed chunks.
    This fence ensures those stale chunks are silently discarded.
    """
    def __init__(self):
        self._current_token: int = 0

    def claim(self) -> int:
        """Claim write ownership. Returns token for this writer."""
        self._current_token += 1
        return self._current_token

    def is_current(self, token: int) -> bool:
        """Check if this writer still holds ownership."""
        return token == self._current_token

    def generation(self) -> int:
        """Current generation number."""
        return self._current_token


class StreamingHeartbeatMonitor:
    """Background liveness pulse generator to prevent proxy/ALB 504 drops during reasoning."""

    def __init__(self, interval: float = 25.0, touch_fn: Optional[Callable[[], Any]] = None):
        self.interval = interval
        self.touch_fn = touch_fn
        self._task: Optional[asyncio.Task] = None
        self._stopped = False

    async def _pulse_loop(self) -> None:
        import inspect
        while not self._stopped:
            try:
                await asyncio.sleep(self.interval)
                if self._stopped:
                    break
                if self.touch_fn:
                    res = self.touch_fn()
                    if inspect.isawaitable(res):
                        await res
                logger.debug("[StreamingHeartbeat] Heartbeat pulse emitted.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[StreamingHeartbeat] Pulse warning: {e}")

    def start(self) -> None:
        self._stopped = False
        self._task = asyncio.create_task(self._pulse_loop())

    def stop(self) -> None:
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()


async def consume_sse_stream(
    response: aiohttp.ClientResponse,
    config: StreamConfig,
    parser: Callable[[dict, StreamResult], bool],
    model_name: str = "unknown",
    fence: Optional[StreamWriterFence] = None,
    fence_token: Optional[int] = None,
    touch_callback: Optional[Callable[[], Any]] = None,
) -> StreamResult:
    """
    Consume SSE stream dari aiohttp response dengan idle timeout.

    Args:
        response: aiohttp response object (sudah connected)
        config: StreamConfig dengan timeout values
        parser: Callable(chunk_json: dict, result: StreamResult) -> bool
                Returns True jika stream selesai (final chunk detected)
        model_name: Untuk logging

    Returns:
        StreamResult dengan accumulated response

    Raises:
        StreamTimeoutError: Jika idle timeout terlampaui
        StreamSafetyTimeoutError: Jika safety timeout terlampaui
    """
    result = StreamResult()
    start_time = time.monotonic()
    last_chunk_time = start_time
    is_first_chunk = True

    buffer = ""
    heartbeat_monitor = StreamingHeartbeatMonitor(interval=25.0, touch_fn=touch_callback)
    heartbeat_monitor.start()

    try:
        while True:
            effective_timeout = (
                config.first_chunk_timeout if is_first_chunk
                else config.idle_timeout
            )
            
            # Read chunk with per-chunk timeout
            try:
                raw_bytes = await asyncio.wait_for(
                    response.content.read(4096),
                    timeout=effective_timeout
                )
            except asyncio.TimeoutError:
                now = time.monotonic()
                timeout_type = "first chunk" if is_first_chunk else "idle"
                raise StreamTimeoutError(
                    f"Streaming {timeout_type} timeout ({effective_timeout:.0f}s) "
                    f"for {model_name} after {result.chunks_received} chunks",
                    idle_seconds=now - last_chunk_time,
                    chunks_received=result.chunks_received,
                    partial_text=result.text[:500]
                )

            if not raw_bytes:
                # EOF reached
                break

            now = time.monotonic()
            elapsed = now - start_time

            # Stale stream fence check
            if fence is not None and fence_token is not None and not fence.is_current(fence_token):
                logger.debug(f"StreamWriterFence: token {fence_token} stale (current {fence.generation()}), aborting")
                result.total_duration = time.monotonic() - start_time
                return result

            # Safety timeout check
            if elapsed > config.safety_timeout:
                raise StreamSafetyTimeoutError(
                    f"Safety timeout {config.safety_timeout:.0f}s exceeded for {model_name} "
                    f"after {result.chunks_received} chunks",
                    idle_seconds=now - last_chunk_time,
                    chunks_received=result.chunks_received,
                    partial_text=result.text[:500]
                )

            chunk_text = raw_bytes.decode("utf-8", errors="replace")
            buffer += chunk_text

            # Process complete SSE events from buffer
            while "\n\n" in buffer or "\r\n\r\n" in buffer:
                # Find event boundary
                sep = "\r\n\r\n" if "\r\n\r\n" in buffer else "\n\n"
                event_text, buffer = buffer.split(sep, 1)

                for line in event_text.split("\n"):
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        continue

                    # SSE comment (keepalive from OpenRouter, etc.)
                    # Counts as liveness signal!
                    if line.startswith(":"):
                        last_chunk_time = time.monotonic()
                        is_first_chunk = False
                        continue

                    # Event type line (Anthropic-style typed SSE)
                    if line.startswith("event:"):
                        continue

                    # Data line
                    if line.startswith("data:"):
                        data_str = line[5:].strip()

                        # End of stream marker
                        if data_str == "[DONE]":
                            result.total_duration = time.monotonic() - start_time
                            return result

                        try:
                            chunk_json = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.debug(f"Skip non-JSON SSE data: {data_str[:100]}")
                            continue

                        # Update liveness
                        last_chunk_time = time.monotonic()
                        result.chunks_received += 1
                        is_first_chunk = False

                        # Let provider-specific parser process chunk
                        is_done = parser(chunk_json, result)
                        if is_done:
                            result.total_duration = time.monotonic() - start_time
                            return result

    except (aiohttp.ClientError, ConnectionError) as e:
        if result.chunks_received > 0:
            logger.warning(
                f"Stream connection lost for {model_name} after "
                f"{result.chunks_received} chunks: {e}"
            )
            result.total_duration = time.monotonic() - start_time
            return result
        raise
    finally:
        heartbeat_monitor.stop()

    result.total_duration = time.monotonic() - start_time
    return result


def _sanitize_url(url: str) -> str:
    """Masks sensitive query parameters (e.g. key, api_key, token) from URL."""
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(str(url))
        if not parsed.query:
            return str(url)
        params = parse_qs(parsed.query)
        sensitive = {"key", "api_key", "apikey", "token", "access_token", "secret"}
        for k in params:
            if k.lower() in sensitive:
                params[k] = ["[REDACTED]"]
        sanitized_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=sanitized_query))
    except Exception:
        return str(url).split("?")[0] + "?[REDACTED]"


async def streaming_request(
    url: str,
    payload: dict,
    headers: dict,
    config: StreamConfig,
    parser: Callable[[dict, StreamResult], bool],
    model_name: str = "unknown",
) -> StreamResult:
    """
    High-level: buat HTTP POST request dan consume SSE stream.

    Menggantikan fetch_with_retry untuk streaming calls.
    """
    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=30.0,
        sock_read=config.first_chunk_timeout + 5.0,
    )

    clean_url = _sanitize_url(url)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status == 429:
                from utils.api.http_retry import RateLimitError
                body = await response.text()
                retry_after = None
                raw_ra = response.headers.get("Retry-After") or response.headers.get("retry-after")
                if raw_ra:
                    try:
                        retry_after = float(raw_ra)
                    except (ValueError, TypeError):
                        pass
                raise RateLimitError(
                    f"HTTP 429 on {clean_url}", body=body,
                    retry_after=retry_after, status=429
                )

            if response.status != 200:
                body = await response.text()
                raise Exception(
                    f"HTTP {response.status} for {clean_url}. Body: {body[:500]}"
                )

            return await consume_sse_stream(
                response, config, parser, model_name
            )
