"""
High-throughput, monotonic tick coalescing and debouncing primitive.
Prevents event-loop starvation by throttling high-frequency tick dispatch per symbol.
"""

from __future__ import annotations

import time
from typing import Dict, Optional


class TickCoalescer:
    """
    Per-symbol monotonic trailing debounce coalescer.
    Ensures tick subscribers are notified at most once per debounce window per symbol.
    """

    def __init__(self, debounce_seconds: float = 0.250) -> None:
        self.debounce_seconds: float = max(0.01, float(debounce_seconds))
        self._last_emitted: Dict[str, float] = {}

    @staticmethod
    def _normalize(symbol: str) -> str:
        if not symbol:
            return ""
        return symbol.strip().upper().replace("/", "")

    def should_emit(self, symbol: str, now_mono: Optional[float] = None) -> bool:
        """
        Returns True if symbol has not been emitted within debounce_seconds.
        Updates internal monotonic timestamp on True.
        """
        sym = self._normalize(symbol)
        if not sym:
            return False

        now = now_mono if now_mono is not None else time.monotonic()
        last = self._last_emitted.get(sym, 0.0)

        if now - last >= self.debounce_seconds:
            self._last_emitted[sym] = now
            if len(self._last_emitted) > 500:
                # Bounded cache hygiene: prune oldest entries
                cutoff = now - (self.debounce_seconds * 10)
                self._last_emitted = {k: v for k, v in self._last_emitted.items() if v >= cutoff}
            return True
        return False

    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset cooldown for a specific symbol or all symbols."""
        if symbol is not None:
            self._last_emitted.pop(self._normalize(symbol), None)
        else:
            self._last_emitted.clear()


_GLOBAL_TICK_COALESCER: Optional[TickCoalescer] = None


def get_tick_coalescer() -> TickCoalescer:
    """Singleton getter for shared application-wide TickCoalescer."""
    global _GLOBAL_TICK_COALESCER
    if _GLOBAL_TICK_COALESCER is None:
        _GLOBAL_TICK_COALESCER = TickCoalescer()
    return _GLOBAL_TICK_COALESCER
