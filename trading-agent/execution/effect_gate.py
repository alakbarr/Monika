# ==============================================================================
# File: execution/effect_gate.py
# ==============================================================================

"""
Effect Gate (Synchronous Side-Effect Admission Gate).

Prevents execution of external mutating operations (such as order submissions to MT5)
if an abort signal or emergency kill-switch has been triggered while orders are
queued or mid-execution.
"""

import asyncio
import logging
from typing import Callable, Any, Optional, TypeVar, Coroutine

logger = logging.getLogger("TradingAgent.Execution.EffectGate")

T = TypeVar("T")


class AbortRequested(Exception):
    """Raised when a side-effect is denied because an abort/kill-switch was triggered."""
    pass


class EffectGateResult:
    """Wrapper result for effect gate execution."""

    def __init__(self, success: bool, result: Any = None, error: Optional[Exception] = None, aborted: bool = False):
        self.success = success
        self.result = result
        self.error = error
        self.aborted = aborted

    def __repr__(self) -> str:
        return f"<EffectGateResult success={self.success} aborted={self.aborted} error={self.error}>"


class EffectGate:
    """
    Synchronous admission gate for mutating side-effect operations (broker order dispatch).

    Guarantees:
    - Atomically checks abort status prior to dispatching mutating payloads to external brokers.
    - If kill-switch or shutdown_event is active, admit() immediately rejects execution.
    - Eliminates race conditions where queued orders might execute after kill-switch invocation.
    """

    def __init__(self):
        self._abort_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._abort_reason: str = ""

    @property
    def is_aborted(self) -> bool:
        """Returns True if the gate is currently aborted."""
        return self._abort_event.is_set()

    @property
    def abort_reason(self) -> str:
        """Returns the reason string for the most recent abort request."""
        return self._abort_reason

    def request_abort(self, reason: str = "Emergency abort requested"):
        """Triggers a synchronous abort signal on the gate."""
        self._abort_reason = reason
        self._abort_event.set()
        logger.warning(f"[EffectGate] ABORT TRIGGERED: {reason}. All future mutating effects blocked.")

    def reset(self):
        """Resets gate status to active (used when trading is resumed)."""
        self._abort_reason = ""
        self._abort_event.clear()
        logger.info("[EffectGate] Gate reset to ACTIVE.")

    async def admit(
        self,
        effect_fn: Callable[[], Coroutine[Any, Any, T]],
        abort_signal: Optional[asyncio.Event] = None,
        context_name: str = "order_submission"
    ) -> T:
        """
        Executes coroutine effect_fn ONLY if no abort signal is active.
        
        Args:
            effect_fn: Zero-argument callable returning a Coroutine
            abort_signal: Optional external asyncio.Event (e.g. shutdown_event)
            context_name: Context identifier for audit logging

        Returns:
            Return value of effect_fn

        Raises:
            AbortRequested: If abort is active prior to or upon admission.
        """
        async with self._lock:
            if self._abort_event.is_set():
                logger.error(
                    f"[EffectGate] ADMISSION BLOCKED for '{context_name}': "
                    f"Gate is aborted ({self._abort_reason})."
                )
                raise AbortRequested(f"Admission blocked: {self._abort_reason}")

            if abort_signal is not None and abort_signal.is_set():
                self._abort_reason = "External abort signal set"
                self._abort_event.set()
                logger.error(
                    f"[EffectGate] ADMISSION BLOCKED for '{context_name}': External abort signal active."
                )
                raise AbortRequested("Admission blocked: External abort signal active")

            logger.debug(f"[EffectGate] Admitted effect '{context_name}'. Executing payload...")
            return await effect_fn()
