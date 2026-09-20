"""
Token Budgeter — Institutional Token Quota and Adaptive Degradation Manager.

Allocates and tracks token consumption across core trading agent subsystems:
- Stage 1 (Macro): 20%
- Stage 2 (Technical/SMC): 45%
- Debate (Dialectic Committee): 15%
- Schedulers & Guardians: 10%
- Emergency Reserve: 10%

Provides real-time quota checks and dynamic degradation tier routing:
- 'normal'     (< 70% quota used): Full thinking, standard context window
- 'compressed' (70% - 90% used): Telegraphic directive, trajectory compaction
- 'degraded'   (>= 90% used): Fast/cheaper tier fallback, skip non-essential runs
"""

import threading
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger("TradingAgent.TokenBudgeter")

SUBSYSTEM_SHARES = {
    "stage1": 0.20,
    "stage2": 0.45,
    "debate": 0.15,
    "schedulers": 0.10,
    "reserve": 0.10,
}

DEFAULT_DAILY_BUDGET = 2_000_000  # Default 2M tokens/day


class TokenBudgetManager:
    """Thread-safe token budget orchestrator with subsystem partitioning and degradation gates."""

    _instance: Optional["TokenBudgetManager"] = None
    _lock = threading.Lock()

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        llm_cfg = self.settings.get("llm", {})
        self.daily_budget = int(llm_cfg.get("daily_token_budget", DEFAULT_DAILY_BUDGET))
        self._current_day = datetime.now(timezone.utc).date()
        self._mu = threading.Lock()

        # Usage counters
        self._usage_by_subsystem: Dict[str, Dict[str, int]] = {
            sub: {"prompt": 0, "completion": 0, "cached": 0, "total": 0}
            for sub in SUBSYSTEM_SHARES
        }
        self._usage_by_model: Dict[str, int] = {}
        self._total_spent = 0

    @classmethod
    def get_instance(cls, settings: Optional[dict] = None) -> "TokenBudgetManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(settings)
            elif settings and not cls._instance.settings:
                cls._instance.settings = settings
            return cls._instance

    def _maybe_reset_daily(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today > self._current_day:
            logger.info(f"[TokenBudgeter] New UTC day ({today}). Resetting daily token counters.")
            self._current_day = today
            self._usage_by_subsystem = {
                sub: {"prompt": 0, "completion": 0, "cached": 0, "total": 0}
                for sub in SUBSYSTEM_SHARES
            }
            self._usage_by_model.clear()
            self._total_spent = 0

    def _normalize_subsystem(self, subsystem: str) -> str:
        s = (subsystem or "").lower().strip()
        if "stage1" in s or "fundamental" in s or "macro" in s:
            return "stage1"
        elif "stage2" in s or "technical" in s or "asset" in s:
            return "stage2"
        elif "debate" in s or "judge" in s or "bull" in s or "bear" in s:
            return "debate"
        elif "sched" in s or "guardian" in s or "watcher" in s or "trigger" in s:
            return "schedulers"
        return "reserve"

    def get_quota(self, subsystem: str) -> int:
        """Returns the daily token quota for the given subsystem."""
        norm = self._normalize_subsystem(subsystem)
        share = SUBSYSTEM_SHARES.get(norm, 0.10)
        return int(self.daily_budget * share)

    def record_usage(
        self,
        subsystem: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "",
        cached_tokens: int = 0,
    ) -> None:
        """Records token spend for a given subsystem and model."""
        with self._mu:
            self._maybe_reset_daily()
            norm = self._normalize_subsystem(subsystem)
            total = prompt_tokens + completion_tokens

            sub_dict = self._usage_by_subsystem.setdefault(
                norm, {"prompt": 0, "completion": 0, "cached": 0, "total": 0}
            )
            sub_dict["prompt"] += prompt_tokens
            sub_dict["completion"] += completion_tokens
            sub_dict["cached"] += cached_tokens
            sub_dict["total"] += total

            self._total_spent += total

            if model:
                self._usage_by_model[model] = self._usage_by_model.get(model, 0) + total

            quota = self.get_quota(norm)
            pct = (sub_dict["total"] / max(1, quota)) * 100.0
            if pct >= 90.0:
                logger.warning(
                    f"[TokenBudgeter] Subsystem '{norm}' consumed {sub_dict['total']}/{quota} tokens ({pct:.1f}% of quota). DEGRADED state."
                )

    def can_spend(self, subsystem: str, estimated_tokens: int = 1000) -> bool:
        """Determines if the subsystem has enough quota remaining to perform the call."""
        with self._mu:
            self._maybe_reset_daily()
            norm = self._normalize_subsystem(subsystem)
            quota = self.get_quota(norm)
            spent = self._usage_by_subsystem.get(norm, {}).get("total", 0)

            # Can spend if within quota or if emergency reserve has room
            if spent + estimated_tokens <= quota:
                return True

            # Check if emergency reserve can buffer
            reserve_spent = self._usage_by_subsystem.get("reserve", {}).get("total", 0)
            reserve_quota = self.get_quota("reserve")
            if reserve_spent + estimated_tokens <= reserve_quota:
                return True

            return False

    def get_degradation_tier(self, subsystem: str) -> str:
        """
        Returns dynamic operational tier:
        - 'normal': Usage < 70% of quota
        - 'compressed': 70% <= Usage < 90% of quota
        - 'degraded': Usage >= 90% of quota
        """
        with self._mu:
            self._maybe_reset_daily()
            norm = self._normalize_subsystem(subsystem)
            quota = self.get_quota(norm)
            spent = self._usage_by_subsystem.get(norm, {}).get("total", 0)

            ratio = spent / max(1, quota)
            if ratio < 0.70:
                return "normal"
            elif ratio < 0.90:
                return "compressed"
            return "degraded"

    def get_budget_summary(self) -> Dict[str, Any]:
        """Provides a detailed JSON-serializable budget report."""
        with self._mu:
            self._maybe_reset_daily()
            subsystem_status = {}
            for sub, share in SUBSYSTEM_SHARES.items():
                quota = int(self.daily_budget * share)
                usage = self._usage_by_subsystem.get(sub, {"total": 0, "prompt": 0, "completion": 0, "cached": 0})
                subsystem_status[sub] = {
                    "quota": quota,
                    "spent": usage["total"],
                    "prompt": usage["prompt"],
                    "completion": usage["completion"],
                    "cached": usage["cached"],
                    "pct_used": round((usage["total"] / max(1, quota)) * 100.0, 1),
                    "tier": "normal" if usage["total"] < 0.7 * quota else ("compressed" if usage["total"] < 0.9 * quota else "degraded"),
                }

            return {
                "date": self._current_day.isoformat(),
                "daily_budget": self.daily_budget,
                "total_spent": self._total_spent,
                "total_pct_used": round((self._total_spent / max(1, self.daily_budget)) * 100.0, 1),
                "subsystems": subsystem_status,
                "models": dict(self._usage_by_model),
            }


def get_token_budgeter(settings: Optional[dict] = None) -> TokenBudgetManager:
    """Convenience accessor for the singleton TokenBudgetManager."""
    return TokenBudgetManager.get_instance(settings)
