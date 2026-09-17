import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("TradingAgent.Execution.HealthCheck")


class FlakeTolerantHealthChecker:
    """Health checker for MT5 connection with caching and transient failure dampening.
    
    Protects against false-alarm disconnect cascades caused by micro-stutters,
    transient socket timeouts, or IPC lock contention.
    """

    def __init__(
        self,
        mt5_client: Any,
        ttl_seconds: float = 30.0,
        grace_seconds: float = 60.0,
        time_provider: Optional[Callable[[], float]] = None,
    ):
        """
        Args:
            mt5_client: MT5Client instance with is_connected() or ping().
            ttl_seconds: Positive result cached for this duration (default 30s).
            grace_seconds: Transient failures suppressed if a successful check occurred within this window (default 60s).
            time_provider: Injectable monotonic time source for deterministic testing.
        """
        self.mt5_client = mt5_client
        self.ttl_seconds = ttl_seconds
        self.grace_seconds = grace_seconds
        self._time_provider = time_provider or time.monotonic
        self._last_success: Optional[float] = None
        self._consecutive_failures: int = 0

    async def is_healthy(self, force_check: bool = False) -> bool:
        """Check MT5 health with TTL cache and grace window suppression."""
        now = self._time_provider()

        # Cached positive check
        if not force_check and self._last_success is not None:
            if (now - self._last_success) < self.ttl_seconds:
                return True

        try:
            # Query client connection state
            if hasattr(self.mt5_client, "is_connected"):
                alive = await self.mt5_client.is_connected()
            elif hasattr(self.mt5_client, "ping"):
                alive = await self.mt5_client.ping()
            else:
                alive = bool(getattr(self.mt5_client, "connected", False))

            if alive:
                self._last_success = now
                self._consecutive_failures = 0
                return True
            else:
                return self._handle_failure(now, reason="is_connected returned False")

        except Exception as exc:
            return self._handle_failure(now, reason=f"Exception: {exc}")

    def _handle_failure(self, now: float, reason: str) -> bool:
        """Evaluate failure against grace period."""
        self._consecutive_failures += 1

        if self._last_success is not None and (now - self._last_success) < self.grace_seconds:
            logger.warning(
                f"MT5 health check transient failure suppressed by grace window "
                f"({now - self._last_success:.1f}s < {self.grace_seconds:.1f}s). Reason: {reason}"
            )
            return True

        logger.error(
            f"MT5 health check failed and grace period expired. "
            f"Consecutive failures: {self._consecutive_failures}. Reason: {reason}"
        )
        return False

    def record_success(self) -> None:
        """Record an explicit external success event (e.g. order placed or ticks fetched)."""
        self._last_success = self._time_provider()
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Immediately invalidate cache and trigger hard failure state."""
        self._last_success = None
        self._consecutive_failures += 1

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic metrics for observability/dashboard."""
        now = self._time_provider()
        age = (now - self._last_success) if self._last_success is not None else None
        cached_valid = age is not None and age < self.ttl_seconds
        in_grace = age is not None and age < self.grace_seconds

        return {
            "cached_valid": cached_valid,
            "in_grace": in_grace,
            "seconds_since_last_success": round(age, 2) if age is not None else None,
            "consecutive_failures": self._consecutive_failures,
        }
