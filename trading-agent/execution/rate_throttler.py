# ==============================================================================
# File: execution/rate_throttler.py
# ==============================================================================

"""
Order Rate Throttler (Leaky-Bucket / Sliding-Window Limiter).

Mencegah pemblokiran akun broker oleh MT5 atau order runaway loop akibat
kegagalan sinkronisasi async atau duplikasi sinyal cepat.

Spesifikasi:
1. Dual-window sliding limiter: Max 2 order/detik, Max 15 order/menit.
2. Thread-safe & asyncio-safe dengan asyncio.Lock.
3. Menghasilkan ThrottleVerdict(allowed, retry_after, reason).
4. Mendukung polling non-blocking (check/acquire) maupun blocking wait (wait_and_acquire).
"""

import asyncio
import time
import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger("TradingAgent.Execution.RateThrottler")


@dataclass(frozen=True)
class ThrottleVerdict:
    """Verdict hasil evaluasi rate limiter order."""
    allowed: bool
    retry_after: float
    reason: str

    def __bool__(self) -> bool:
        return self.allowed


class RateThrottler:
    """
    Sliding-window order rate limiter.
    
    Menjaga frekuensi pengiriman order ke broker (MT5) agar tidak melampaui:
    - Per-second limit (default: 2 order / detik)
    - Per-minute limit (default: 15 order / menit)
    """

    def __init__(
        self,
        max_per_second: int = 2,
        max_per_minute: int = 15,
        settings: Optional[Dict[str, Any]] = None,
    ):
        if settings:
            cfg = settings.get("execution", {}).get("rate_limiter", {})
            self.max_per_second = max(1, int(cfg.get("max_per_second", max_per_second)))
            self.max_per_minute = max(1, int(cfg.get("max_per_minute", max_per_minute)))
        else:
            self.max_per_second = max(1, int(max_per_second))
            self.max_per_minute = max(1, int(max_per_minute))

        self._second_window: deque[float] = deque()
        self._minute_window: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _cleanup_windows(self, now: float) -> None:
        """Prune timestamps older than the respective windows."""
        one_sec_ago = now - 1.0
        while self._second_window and self._second_window[0] <= one_sec_ago:
            self._second_window.popleft()

        one_min_ago = now - 60.0
        while self._minute_window and self._minute_window[0] <= one_min_ago:
            self._minute_window.popleft()

    async def check(self, now: Optional[float] = None) -> ThrottleVerdict:
        """
        Periksa apakah slot order tersedia tanpa mengonsumsi kuota.
        """
        async with self._lock:
            ts = now if now is not None else time.monotonic()
            self._cleanup_windows(ts)

            # Check 1-second limit
            if self._second_window and len(self._second_window) >= self.max_per_second:
                oldest_in_sec = self._second_window[0]
                retry_after = max(0.01, round(1.0 - (ts - oldest_in_sec), 3))
                return ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Second rate limit exceeded ({len(self._second_window)}/{self.max_per_second} in 1s)",
                )

            # Check 1-minute limit
            if self._minute_window and len(self._minute_window) >= self.max_per_minute:
                oldest_in_min = self._minute_window[0]
                retry_after = max(0.1, round(60.0 - (ts - oldest_in_min), 3))
                return ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Minute rate limit exceeded ({len(self._minute_window)}/{self.max_per_minute} in 60s)",
                )

            return ThrottleVerdict(allowed=True, retry_after=0.0, reason="OK")

    async def acquire(self, now: Optional[float] = None) -> ThrottleVerdict:
        """
        Cek dan konsumsi 1 slot order jika diizinkan (non-blocking).
        """
        async with self._lock:
            ts = now if now is not None else time.monotonic()
            self._cleanup_windows(ts)

            if self._second_window and len(self._second_window) >= self.max_per_second:
                oldest_in_sec = self._second_window[0]
                retry_after = max(0.01, round(1.0 - (ts - oldest_in_sec), 3))
                verdict = ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Second rate limit exceeded ({len(self._second_window)}/{self.max_per_second} in 1s)",
                )
                logger.warning(f"[RateThrottler] BLOCKED: {verdict.reason}, retry_after={retry_after}s")
                return verdict

            if self._minute_window and len(self._minute_window) >= self.max_per_minute:
                oldest_in_min = self._minute_window[0]
                retry_after = max(0.1, round(60.0 - (ts - oldest_in_min), 3))
                verdict = ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Minute rate limit exceeded ({len(self._minute_window)}/{self.max_per_minute} in 60s)",
                )
                logger.warning(f"[RateThrottler] BLOCKED: {verdict.reason}, retry_after={retry_after}s")
                return verdict

            # Konsumsi slot
            self._second_window.append(ts)
            self._minute_window.append(ts)
            logger.debug(
                f"[RateThrottler] Order slot acquired. (1s: {len(self._second_window)}/{self.max_per_second}, "
                f"60s: {len(self._minute_window)}/{self.max_per_minute})"
            )
            return ThrottleVerdict(allowed=True, retry_after=0.0, reason="Acquired")

    async def wait_and_acquire(self, timeout: float = 10.0) -> ThrottleVerdict:
        """
        Tunggu hingga slot tersedia atau timeout tercapai.
        Jika timeout <= 0, lakukan 1 kali percobaan (non-blocking).
        """
        verdict = await self.acquire()
        if verdict.allowed or timeout <= 0:
            return verdict

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sleep_time = min(verdict.retry_after, deadline - time.monotonic())
            if sleep_time <= 0:
                break
            await asyncio.sleep(sleep_time)
            verdict = await self.acquire()
            if verdict.allowed:
                return verdict

        return ThrottleVerdict(
            allowed=False,
            retry_after=verdict.retry_after,
            reason=f"Timed out waiting for order slot after {timeout}s",
        )

    async def reset(self) -> None:
        """Reset internal rate tracking windows."""
        async with self._lock:
            self._second_window.clear()
            self._minute_window.clear()
