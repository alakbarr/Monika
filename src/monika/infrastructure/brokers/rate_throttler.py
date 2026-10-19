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
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

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

        self._windows: Dict[str, Tuple[deque[float], deque[float]]] = {}
        self._second_window: deque[float] = deque()
        self._minute_window: deque[float] = deque()
        self._windows["orders"] = (self._second_window, self._minute_window)
        self._lock = asyncio.Lock()

    def _get_category_limits(self, category: str) -> Tuple[int, int]:
        if category == "modifications":
            return max(self.max_per_second * 2, 5), max(self.max_per_minute * 2, 30)
        return self.max_per_second, self.max_per_minute

    def _cleanup_windows(self, now: float, category: str = "orders") -> Tuple[deque[float], deque[float]]:
        """Prune timestamps older than the respective windows."""
        if category not in self._windows:
            self._windows[category] = (deque(), deque())
        sec_win, min_win = self._windows[category]

        one_sec_ago = now - 1.0
        while sec_win and sec_win[0] <= one_sec_ago:
            sec_win.popleft()

        one_min_ago = now - 60.0
        while min_win and min_win[0] <= one_min_ago:
            min_win.popleft()

        return sec_win, min_win

    async def check(self, now: Optional[float] = None, category: str = "orders") -> ThrottleVerdict:
        """
        Periksa apakah slot order tersedia tanpa mengonsumsi kuota.
        Emergency actions selalu diizinkan tanpa rate limiting.
        """
        if category == "emergency":
            return ThrottleVerdict(allowed=True, retry_after=0.0, reason="Emergency bypass")

        async with self._lock:
            ts = now if now is not None else time.monotonic()
            sec_win, min_win = self._cleanup_windows(ts, category=category)
            max_sec, max_min = self._get_category_limits(category)

            # Check 1-second limit
            if sec_win and len(sec_win) >= max_sec:
                oldest_in_sec = sec_win[0]
                retry_after = max(0.01, round(1.0 - (ts - oldest_in_sec), 3))
                return ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Second rate limit exceeded for {category} ({len(sec_win)}/{max_sec} in 1s)",
                )

            # Check 1-minute limit
            if min_win and len(min_win) >= max_min:
                oldest_in_min = min_win[0]
                retry_after = max(0.1, round(60.0 - (ts - oldest_in_min), 3))
                return ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Minute rate limit exceeded for {category} ({len(min_win)}/{max_min} in 60s)",
                )

            return ThrottleVerdict(allowed=True, retry_after=0.0, reason="OK")

    async def acquire(self, now: Optional[float] = None, category: str = "orders") -> ThrottleVerdict:
        """
        Cek dan konsumsi 1 slot order jika diizinkan (non-blocking).
        Emergency actions selalu diizinkan.
        """
        if category == "emergency":
            return ThrottleVerdict(allowed=True, retry_after=0.0, reason="Emergency bypass")

        async with self._lock:
            ts = now if now is not None else time.monotonic()
            sec_win, min_win = self._cleanup_windows(ts, category=category)
            max_sec, max_min = self._get_category_limits(category)

            if sec_win and len(sec_win) >= max_sec:
                oldest_in_sec = sec_win[0]
                retry_after = max(0.01, round(1.0 - (ts - oldest_in_sec), 3))
                verdict = ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Second rate limit exceeded for {category} ({len(sec_win)}/{max_sec} in 1s)",
                )
                logger.warning(f"[RateThrottler] BLOCKED: {verdict.reason}, retry_after={retry_after}s")
                return verdict

            if min_win and len(min_win) >= max_min:
                oldest_in_min = min_win[0]
                retry_after = max(0.1, round(60.0 - (ts - oldest_in_min), 3))
                verdict = ThrottleVerdict(
                    allowed=False,
                    retry_after=retry_after,
                    reason=f"Minute rate limit exceeded for {category} ({len(min_win)}/{max_min} in 60s)",
                )
                logger.warning(f"[RateThrottler] BLOCKED: {verdict.reason}, retry_after={retry_after}s")
                return verdict

            # Konsumsi slot
            sec_win.append(ts)
            min_win.append(ts)
            logger.debug(
                f"[RateThrottler] {category} slot acquired. (1s: {len(sec_win)}/{max_sec}, "
                f"60s: {len(min_win)}/{max_min})"
            )
            return ThrottleVerdict(allowed=True, retry_after=0.0, reason="Acquired")

    async def wait_and_acquire(self, timeout: float = 10.0, category: str = "orders") -> ThrottleVerdict:
        """
        Tunggu hingga slot tersedia atau timeout tercapai.
        Jika timeout <= 0, lakukan 1 kali percobaan (non-blocking).
        """
        verdict = await self.acquire(category=category)
        if verdict.allowed or timeout <= 0:
            return verdict

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sleep_time = min(verdict.retry_after, deadline - time.monotonic())
            if sleep_time <= 0:
                break
            await asyncio.sleep(sleep_time)
            verdict = await self.acquire(category=category)
            if verdict.allowed:
                return verdict

        return ThrottleVerdict(
            allowed=False,
            retry_after=verdict.retry_after,
            reason=f"Timed out waiting for {category} order slot after {timeout}s",
        )

    async def reset(self) -> None:
        """Reset internal rate tracking windows."""
        async with self._lock:
            for sec_win, min_win in self._windows.values():
                sec_win.clear()
                min_win.clear()
