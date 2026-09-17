"""
Multi-provider Credential Pooling and Automatic Rotation (Phase 8 - I7).
NOTE: For global application-wide credential management, see `utils.api.credential_pool.CredentialPool`.
This module provides the async per-provider key iterator variant.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
import time
from typing import Dict, List, Optional

logger = logging.getLogger("TradingAgent.LLM.CredentialPool")


@dataclass
class CredentialState:
    """Tracks health and cooldown of an individual API key."""
    key: str
    provider: str
    cooldown_until: float = 0.0
    failure_count: int = 0
    success_count: int = 0

    def is_available(self) -> bool:
        """Check if credential is not currently cooling down."""
        return time.time() >= self.cooldown_until

    def mark_rate_limited(self, cooldown_seconds: float = 60.0) -> None:
        """Put credential on cooldown after rate limit (429)."""
        self.cooldown_until = time.time() + cooldown_seconds
        self.failure_count += 1
        logger.warning(
            f"[{self.provider}] Credential ...{self.key[-4:] if len(self.key) >= 4 else '***'} "
            f"rate limited. Cooling down for {cooldown_seconds}s."
        )

    def mark_success(self) -> None:
        """Record successful call."""
        self.success_count += 1
        self.failure_count = 0


class LLMCredentialPool:
    """Thread-safe multi-provider API credential pool with health-aware rotation."""

    def __init__(self, provider: str, keys: Optional[List[str]] = None):
        self.provider = provider
        self._states: List[CredentialState] = [
            CredentialState(key=k.strip(), provider=provider)
            for k in (keys or []) if k and k.strip()
        ]
        self._current_index: int = 0
        self._lock = asyncio.Lock()

    @classmethod
    def from_env(cls, provider: str, env_vars: List[str]) -> "LLMCredentialPool":
        """Build a credential pool by inspecting multiple comma-separated environment variables."""
        collected_keys: List[str] = []
        for var in env_vars:
            val = os.getenv(var, "").strip()
            if val:
                for k in val.split(","):
                    k = k.strip()
                    if k and k not in collected_keys:
                        collected_keys.append(k)
        return cls(provider=provider, keys=collected_keys)

    def total_keys(self) -> int:
        return len(self._states)

    async def get_active_key(self) -> Optional[str]:
        """Get next available healthy API key via round-robin."""
        if not self._states:
            return None

        async with self._lock:
            n = len(self._states)
            for _ in range(n):
                idx = self._current_index % n
                state = self._states[idx]
                self._current_index += 1
                if state.is_available():
                    return state.key

            # All keys are currently in cooldown; return the one with earliest cooldown expiry
            earliest = min(self._states, key=lambda s: s.cooldown_until)
            logger.warning(f"[{self.provider}] All {n} credentials in cooldown. Using earliest.")
            return earliest.key

    async def report_rate_limited(self, key: str, cooldown_seconds: float = 60.0) -> None:
        """Flag key as rate limited."""
        async with self._lock:
            for state in self._states:
                if state.key == key:
                    state.mark_rate_limited(cooldown_seconds)
                    break

    async def report_success(self, key: str) -> None:
        """Flag key as healthy."""
        async with self._lock:
            for state in self._states:
                if state.key == key:
                    state.mark_success()
                    break


# Backward-compatibility alias
CredentialPool = LLMCredentialPool
