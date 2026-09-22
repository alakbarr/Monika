"""
Monika Unified Credential Pool & Multi-Key Health Tracker.
Supports dynamic key rotation, health scoring, exponential cooldowns (60s -> 4h),
cost tracking, model-level cooldowns, and seamless integration with FailoverReason.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Any, Union

from provider.error_taxonomy import FailoverReason

logger = logging.getLogger("TradingAgent.Provider.CredentialPool")


@dataclass
class KeyHealth:
    """Tracks health, usage, rate limits, and financial metrics of an individual API key."""
    key: str
    provider: str
    is_active: bool = True
    cooldown_until: float = 0.0
    consecutive_errors: int = 0
    consecutive_rate_limits: int = 0
    total_requests: int = 0
    total_errors: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    last_used: float = 0.0
    disabled_reason: Optional[str] = None
    model_cooldowns: Dict[str, float] = field(default_factory=dict)

    @property
    def is_in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    @property
    def is_available(self) -> bool:
        return self.is_active and not self.is_in_cooldown

    def is_model_available(self, model: Optional[str] = None) -> bool:
        if not self.is_available:
            return False
        if model:
            cd = self.model_cooldowns.get(model, 0.0)
            if time.time() < cd:
                return False
        return True

    def calculate_exponential_cooldown(
        self,
        base_seconds: float = 60.0,
        max_seconds: float = 14400.0,  # 4 hours max
    ) -> float:
        """Calculate exponential backoff cooldown based on consecutive rate limit encounters."""
        multiplier = 2 ** max(0, self.consecutive_rate_limits - 1)
        cd = min(max_seconds, base_seconds * multiplier)
        return float(cd)

    def mark_rate_limited(
        self,
        cooldown_seconds: float = 60.0,
        model: Optional[str] = None,
        retry_after: Optional[float] = None,
        reset_at: Optional[float] = None,
        base_seconds: float = 60.0,
        max_seconds: float = 14400.0,
    ) -> float:
        """Arm key or model-level rate limit cooldown with exponential backoff & header hint support."""
        self.consecutive_rate_limits += 1
        self.consecutive_errors += 1
        self.total_errors += 1

        if retry_after is not None and retry_after > 0:
            effective_cd = float(retry_after)
        elif reset_at is not None:
            effective_cd = max(1.0, float(reset_at) - time.time())
        elif cooldown_seconds != 60.0:
            effective_cd = float(cooldown_seconds)
        else:
            effective_cd = self.calculate_exponential_cooldown(base_seconds, max_seconds)

        now = time.time()
        masked = self.key[:6] + "..." + self.key[-4:] if len(self.key) > 12 else "***"

        if model:
            self.model_cooldowns[model] = now + effective_cd
            logger.warning(
                f"[CredentialPool] Model '{model}' on key {masked} ({self.provider}) rate limited "
                f"(hit #{self.consecutive_rate_limits}). Cooldown {effective_cd:.1f}s."
            )
        else:
            self.cooldown_until = now + effective_cd
            logger.warning(
                f"[CredentialPool] Key {masked} ({self.provider}) rate limited "
                f"(hit #{self.consecutive_rate_limits}). Cooldown {effective_cd:.1f}s."
            )

        return effective_cd

    def mark_success(self, tokens: int = 0, cost_usd: float = 0.0) -> None:
        """Record successful invocation, resetting consecutive error counters."""
        self.consecutive_errors = 0
        self.consecutive_rate_limits = 0
        self.total_requests += 1
        self.total_tokens += tokens
        self.total_cost_usd += cost_usd

    def mark_failure(
        self,
        reason: Union[FailoverReason, str] = FailoverReason.UNKNOWN,
        is_permanent: bool = False,
    ) -> None:
        """Record non-rate-limit error (e.g. auth, billing, transient 5xx)."""
        self.consecutive_errors += 1
        self.total_errors += 1
        masked = self.key[:6] + "..." + self.key[-4:] if len(self.key) > 12 else "***"

        reason_str = str(reason.value if isinstance(reason, FailoverReason) else reason).lower()

        # Permanent failure conditions
        if (
            is_permanent
            or reason in (FailoverReason.AUTH_PERMANENT, FailoverReason.AUTH_ERROR, FailoverReason.BILLING_EXHAUSTED, FailoverReason.HARD_QUOTA_EXHAUSTED)
            or any(m in reason_str for m in ("invalid_api_key", "unauthorized", "quota exceeded", "billing", "insufficient_quota"))
        ):
            self.is_active = False
            self.disabled_reason = reason_str or "Permanent credential rejection"
            logger.error(f"[CredentialPool] Permanently disabled key {masked} ({self.provider}): {self.disabled_reason}")
            return

        # 5 consecutive transient errors trigger a safety cooldown
        if self.consecutive_errors >= 5:
            self.cooldown_until = time.time() + 120.0
            logger.warning(f"[CredentialPool] Key {masked} ({self.provider}) hit 5 consecutive errors. 120s safety cooldown.")


# Backward-compatible alias for per-key dataclass
CredentialState = KeyHealth


class CredentialPool:
    """
    Unified multi-provider credential registry with multi-key health tracking,
    exponential cooldown backoff, model-level cooldowns, and usage telemetry.
    """

    def __init__(
        self,
        base_cooldown_seconds: float = 60.0,
        max_cooldown_seconds: float = 14400.0,
        auto_init_env: bool = True,
    ):
        self.base_cooldown_seconds = base_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self._pools: Dict[str, List[KeyHealth]] = {}
        self._lock = asyncio.Lock()
        if auto_init_env:
            self._initialize_from_env()

    def _initialize_from_env(self) -> None:
        """Populate initial keys from environment variables across all supported providers."""
        provider_env_map = {
            "gemini": ["GEMINI_API_KEYS", "GEMINI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEY"],
            "openai": ["OPENAI_API_KEYS", "OPENAI_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY"],
            "groq": ["GROQ_API_KEYS", "GROQ_API_KEY"],
            "openrouter": ["OPENROUTER_API_KEYS", "OPENROUTER_API_KEY"],
            "typesafe": ["TYPESAFE_API_KEYS", "TYPESAFE_API_KEY"],
        }

        for prov, env_vars in provider_env_map.items():
            for var in env_vars:
                val = os.getenv(var, "").strip()
                if val:
                    for k in [k.strip() for k in val.split(",") if k.strip()]:
                        self.add_key(prov, k)

    def add_key(self, provider: str, key: str) -> None:
        """Add a key to the provider's pool if not already present."""
        prov = provider.lower()
        if prov not in self._pools:
            self._pools[prov] = []

        for kh in self._pools[prov]:
            if kh.key == key:
                return

        self._pools[prov].append(KeyHealth(key=key, provider=prov))
        masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "***"
        logger.debug(f"[CredentialPool] Registered key {masked} for provider '{prov}'")

    def total_keys(self, provider: Optional[str] = None) -> int:
        """Return total keys count for a provider or across all providers."""
        if provider:
            return len(self._pools.get(provider.lower(), []))
        return sum(len(keys) for keys in self._pools.values())

    def is_model_available(self, model: str, provider: Optional[str] = None) -> bool:
        """Check if at least one active key is available without active cooldown for the model."""
        if provider:
            keys = self._pools.get(provider.lower(), [])
            return any(k.is_model_available(model) for k in keys) if keys else True
        for keys in self._pools.values():
            if any(k.is_model_available(model) for k in keys):
                return True
        return True

    def get_key(
        self,
        provider: str,
        model: Optional[str] = None,
        is_hot_path: bool = False,
        task_role: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get best available API key for provider (LRU round-robin).
        If is_hot_path is True and all keys are in cooldown, returns None immediately.
        """
        prov = provider.lower()
        keys = self._pools.get(prov, [])
        if not keys:
            return None

        available = [k for k in keys if k.is_model_available(model)]
        if not available:
            cooldown_keys = [k for k in keys if k.is_active]
            if cooldown_keys:
                earliest = min(cooldown_keys, key=lambda x: x.cooldown_until)
                rem = max(0.0, earliest.cooldown_until - time.time())
                logger.warning(
                    f"[CredentialPool] All keys for '{prov}' (model={model}) in cooldown. "
                    f"Earliest ready in {rem:.1f}s. "
                    f"{'Hot-path active: returning None for instant failover.' if is_hot_path else ''}"
                )
            return None

        # Sort by last_used ascending (LRU)
        selected = min(available, key=lambda x: x.last_used)
        selected.last_used = time.time()
        return selected.key

    async def get_active_key(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """Async-safe key retrieval."""
        async with self._lock:
            prov = provider or "gemini"
            return self.get_key(provider=prov, model=model)

    def report_success(
        self,
        provider: str,
        key: str,
        model: Optional[str] = None,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Report successful request on key."""
        prov = provider.lower()
        for kh in self._pools.get(prov, []):
            if kh.key == key:
                kh.mark_success(tokens=tokens, cost_usd=cost_usd)
                return

    def report_rate_limit(
        self,
        provider: str,
        key: str,
        cooldown_seconds: float = 60.0,
        model: Optional[str] = None,
        retry_after: Optional[float] = None,
        reset_at: Optional[float] = None,
    ) -> float:
        """Report rate limit on key, arming exponential cooldown."""
        prov = provider.lower()
        for kh in self._pools.get(prov, []):
            if kh.key == key:
                return kh.mark_rate_limited(
                    cooldown_seconds=cooldown_seconds,
                    model=model,
                    retry_after=retry_after,
                    reset_at=reset_at,
                    base_seconds=self.base_cooldown_seconds,
                    max_seconds=self.max_cooldown_seconds,
                )
        return cooldown_seconds

    def report_failure(
        self,
        provider: str,
        key: str,
        reason: Union[FailoverReason, str] = FailoverReason.UNKNOWN,
        is_permanent: bool = False,
        model: Optional[str] = None,
    ) -> None:
        """Report failure on key (auth, quota, network, or server error)."""
        prov = provider.lower()
        for kh in self._pools.get(prov, []):
            if kh.key == key:
                kh.mark_failure(reason=reason, is_permanent=is_permanent)
                return

    def all_exhausted(self, provider: str, model: Optional[str] = None) -> bool:
        """Check if all keys for a provider are in cooldown or disabled."""
        prov = provider.lower()
        keys = self._pools.get(prov, [])
        if not keys:
            return True
        return not any(k.is_model_available(model) for k in keys)

    def get_cumulative_cost(self, provider: Optional[str] = None) -> float:
        """Get total cost in USD tracked across keys."""
        if provider:
            return sum(k.total_cost_usd for k in self._pools.get(provider.lower(), []))
        return sum(sum(k.total_cost_usd for k in keys) for keys in self._pools.values())

    def get_pool_status(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Return diagnostic metrics of all keys in pool."""
        now = time.time()
        result = {}
        provs = [provider.lower()] if provider else list(self._pools.keys())
        for p in provs:
            entries = []
            for kh in self._pools.get(p, []):
                entries.append({
                    "masked_key": kh.key[:6] + "..." + kh.key[-4:] if len(kh.key) > 12 else "***",
                    "is_active": kh.is_active,
                    "is_available": kh.is_available,
                    "cooldown_remaining_sec": max(0.0, kh.cooldown_until - now),
                    "consecutive_rate_limits": kh.consecutive_rate_limits,
                    "consecutive_errors": kh.consecutive_errors,
                    "total_requests": kh.total_requests,
                    "total_errors": kh.total_errors,
                    "total_tokens": kh.total_tokens,
                    "total_cost_usd": kh.total_cost_usd,
                    "disabled_reason": kh.disabled_reason,
                })
            result[p] = entries
        return result


class LLMCredentialPool:
    """
    Per-provider async credential pool wrapper, maintaining full backward
    compatibility with Phase 8 tests and utils/llm/credential_pool.py.
    """

    def __init__(self, provider: str, keys: Optional[List[str]] = None):
        self.provider = provider.lower()
        self._states: List[CredentialState] = [
            CredentialState(key=k.strip(), provider=self.provider)
            for k in (keys or []) if k and k.strip()
        ]
        self._current_index: int = 0
        self._lock = asyncio.Lock()

    @classmethod
    def from_env(cls, provider: str, env_vars: List[str]) -> "LLMCredentialPool":
        collected: List[str] = []
        for var in env_vars:
            val = os.getenv(var, "").strip()
            if val:
                for k in val.split(","):
                    k = k.strip()
                    if k and k not in collected:
                        collected.append(k)
        return cls(provider=provider, keys=collected)

    def total_keys(self) -> int:
        return len(self._states)

    async def get_active_key(self) -> Optional[str]:
        if not self._states:
            return None

        async with self._lock:
            n = len(self._states)
            for _ in range(n):
                idx = self._current_index % n
                state = self._states[idx]
                self._current_index += 1
                if state.is_available:
                    state.last_used = time.time()
                    return state.key

            earliest = min(self._states, key=lambda s: s.cooldown_until)
            logger.warning(f"[{self.provider}] All {n} credentials in cooldown. Using earliest.")
            return earliest.key

    async def report_rate_limited(self, key: str, cooldown_seconds: float = 60.0) -> None:
        async with self._lock:
            for state in self._states:
                if state.key == key:
                    state.mark_rate_limited(cooldown_seconds)
                    break

    async def report_success(self, key: str) -> None:
        async with self._lock:
            for state in self._states:
                if state.key == key:
                    state.mark_success()
                    break


# Compatibility Aliases
APICredentialPool = CredentialPool

_GLOBAL_CREDENTIAL_POOL: Optional[CredentialPool] = None


def get_credential_pool() -> CredentialPool:
    """Get singleton CredentialPool instance."""
    global _GLOBAL_CREDENTIAL_POOL
    if _GLOBAL_CREDENTIAL_POOL is None:
        _GLOBAL_CREDENTIAL_POOL = CredentialPool()
    return _GLOBAL_CREDENTIAL_POOL
