"""
Runtime Model Registry for Dynamic Zero-Downtime Hot-Swapping.
Allows changing the primary or fallback model of any task role at runtime
(e.g., via Telegram command /model or config reload) without restarting the agent.
"""

import logging
import threading
from typing import Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.RuntimeModelRegistry")


class RuntimeModelRegistry:
    """Thread-safe registry for runtime dynamic model overrides per task role."""

    _instance: Optional["RuntimeModelRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._overrides: Dict[str, Dict[str, str]] = {}  # task_role -> {"primary": model, "fallback_1": model}
        self._rw_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "RuntimeModelRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_role_model(self, task_role: str, model_name: str, slot: str = "primary") -> None:
        """Dynamically override the model for a specific task role and slot."""
        with self._rw_lock:
            if task_role not in self._overrides:
                self._overrides[task_role] = {}
            self._overrides[task_role][slot] = model_name
            logger.info(f"[RuntimeModelRegistry] Hot-swapped role '{task_role}' [{slot}] -> '{model_name}'")

    def get_role_model(self, task_role: str, slot: str = "primary") -> Optional[str]:
        """Get the active runtime override for a role slot, if any."""
        with self._rw_lock:
            return self._overrides.get(task_role, {}).get(slot)

    def clear_overrides(self, task_role: Optional[str] = None) -> None:
        """Reset runtime overrides to defaults defined in settings.yaml."""
        with self._rw_lock:
            if task_role:
                self._overrides.pop(task_role, None)
                logger.info(f"[RuntimeModelRegistry] Reset overrides for role '{task_role}' to config defaults")
            else:
                self._overrides.clear()
                logger.info("[RuntimeModelRegistry] Cleared all runtime model overrides")

    def get_all_overrides(self) -> Dict[str, Dict[str, str]]:
        with self._rw_lock:
            return {k: dict(v) for k, v in self._overrides.items()}
