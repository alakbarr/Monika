"""
Cycle Budget Guard — Menjaga dan membatasi konsumsi token LLM per siklus trading.

Fitur:
- Tracking akumulasi input_tokens, output_tokens, thinking_tokens, cached_tokens, dan cost_usd.
- Memberikan peringatan dan pencegahan (hard abort) jika konsumsi melebihi batas budget per siklus.
- Mencegah recursive thinking loop atau runaway tool loops yang membuang kuota token.
"""

import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("TradingAgent.CycleBudgetGuard")


class CycleBudgetGuard:
    """
    Guard untuk mengawasi akumulasi penggunaan token dalam satu siklus analisis.
    """

    def __init__(
        self,
        max_input_tokens: int = 1_000_000,
        max_output_tokens: int = 150_000,
        max_cost_usd: float = 5.0,
        enabled: bool = True,
    ):
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.max_cost_usd = max_cost_usd
        self.enabled = enabled

        self._input_used = 0
        self._output_used = 0
        self._thinking_used = 0
        self._cached_used = 0
        self._cost_usd_used = 0.0

    @classmethod
    def from_settings(cls, settings: Optional[dict] = None) -> "CycleBudgetGuard":
        cfg = (settings or {}).get("llm", {}).get("cycle_budget", {})
        return cls(
            max_input_tokens=int(cfg.get("max_input_tokens", 1_000_000)),
            max_output_tokens=int(cfg.get("max_output_tokens", 150_000)),
            max_cost_usd=float(cfg.get("max_cost_usd", 5.0)),
            enabled=bool(cfg.get("enabled", True)),
        )

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int = 0,
        cached_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Mencatat token yang digunakan oleh satu panggilan LLM."""
        self._input_used += max(0, int(input_tokens or 0))
        self._output_used += max(0, int(output_tokens or 0))
        self._thinking_used += max(0, int(thinking_tokens or 0))
        self._cached_used += max(0, int(cached_tokens or 0))
        self._cost_usd_used += max(0.0, float(cost_usd or 0.0))

    def check(self) -> Tuple[bool, str]:
        """
        Memeriksa apakah budget token siklus masih aman.
        Returns:
            (is_allowed: bool, reason: str)
        """
        if not self.enabled:
            return True, "budget_guard_disabled"

        if self._input_used >= self.max_input_tokens:
            msg = f"Input token budget exceeded ({self._input_used:,}/{self.max_input_tokens:,})"
            logger.error(f"[CycleBudgetGuard] {msg}")
            return False, msg

        if self._output_used >= self.max_output_tokens:
            msg = f"Output token budget exceeded ({self._output_used:,}/{self.max_output_tokens:,})"
            logger.error(f"[CycleBudgetGuard] {msg}")
            return False, msg

        if self.max_cost_usd > 0 and self._cost_usd_used >= self.max_cost_usd:
            msg = f"Cost budget exceeded (${self._cost_usd_used:.4f}/${self.max_cost_usd:.2f})"
            logger.error(f"[CycleBudgetGuard] {msg}")
            return False, msg

        return True, "ok"

    def is_exceeded(self) -> bool:
        """Helper boolean untuk pemeriksaan cepat."""
        allowed, _ = self.check()
        return not allowed

    def get_stats(self) -> Dict[str, Any]:
        """Mengembalikan statistik konsumsi token siklus saat ini."""
        return {
            "input_used": self._input_used,
            "output_used": self._output_used,
            "thinking_used": self._thinking_used,
            "cached_used": self._cached_used,
            "total_tokens": self._input_used + self._output_used,
            "cost_usd_used": round(self._cost_usd_used, 4),
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_usd": self.max_cost_usd,
            "enabled": self.enabled,
        }

    def reset(self) -> None:
        """Reset counter di awal siklus baru."""
        self._input_used = 0
        self._output_used = 0
        self._thinking_used = 0
        self._cached_used = 0
        self._cost_usd_used = 0.0
        logger.debug("[CycleBudgetGuard] Budget counters reset for new cycle.")


_global_guard: Optional[CycleBudgetGuard] = None


def get_cycle_budget_guard(settings: Optional[dict] = None) -> CycleBudgetGuard:
    """Mengambil atau menginisialisasi singleton instance CycleBudgetGuard."""
    global _global_guard
    if _global_guard is None:
        _global_guard = CycleBudgetGuard.from_settings(settings)
    return _global_guard
