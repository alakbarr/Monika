# ==============================================================================
# File: utils/api/credential_pool.py
# ==============================================================================

"""
Credential Pool & Multi-Key Health Tracker (M2).
Provides dynamic API key rotation, health scoring, and automatic cooldown.
"""

import time
import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger("TradingAgent.CredentialPool")


@dataclass
class KeyHealth:
    key: str
    provider: str
    is_active: bool = True
    cooldown_until: float = 0.0
    consecutive_errors: int = 0
    total_requests: int = 0
    total_errors: int = 0
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


class APICredentialPool:
    """Manages pool of credentials across multiple LLM and data providers."""

    def __init__(self):
        self._pools: Dict[str, List[KeyHealth]] = {}
        self._initialize_from_env()

    def _initialize_from_env(self) -> None:
        """Populate initial keys from loaded environment variables."""
        # Gemini (supports comma-separated list or single key)
        gemini_raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
        for k in [k.strip() for k in gemini_raw.split(",") if k.strip()]:
            self.add_key("gemini", k)

        # Anthropic
        anthropic_raw = os.getenv("ANTHROPIC_API_KEYS", "") or os.getenv("ANTHROPIC_API_KEY", "")
        for k in [k.strip() for k in anthropic_raw.split(",") if k.strip()]:
            self.add_key("anthropic", k)

        # OpenAI
        openai_raw = os.getenv("OPENAI_API_KEYS", "") or os.getenv("OPENAI_API_KEY", "")
        for k in [k.strip() for k in openai_raw.split(",") if k.strip()]:
            self.add_key("openai", k)

        # DeepSeek
        deepseek_raw = os.getenv("DEEPSEEK_API_KEYS", "") or os.getenv("DEEPSEEK_API_KEY", "")
        for k in [k.strip() for k in deepseek_raw.split(",") if k.strip()]:
            self.add_key("deepseek", k)

        # Groq (supports comma-separated list or single key)
        groq_raw = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
        for k in [k.strip() for k in groq_raw.split(",") if k.strip()]:
            self.add_key("groq", k)

        # OpenRouter
        openrouter_raw = os.getenv("OPENROUTER_API_KEYS", "") or os.getenv("OPENROUTER_API_KEY", "")
        for k in [k.strip() for k in openrouter_raw.split(",") if k.strip()]:
            self.add_key("openrouter", k)

        # TypeSafe
        typesafe_raw = os.getenv("TYPESAFE_API_KEYS", "") or os.getenv("TYPESAFE_API_KEY", "")
        for k in [k.strip() for k in typesafe_raw.split(",") if k.strip()]:
            self.add_key("typesafe", k)

    def add_key(self, provider: str, key: str) -> None:
        """Add a key to the pool if not already present."""
        prov = provider.lower()
        if prov not in self._pools:
            self._pools[prov] = []

        # Avoid duplicates
        for kh in self._pools[prov]:
            if kh.key == key:
                return

        self._pools[prov].append(KeyHealth(key=key, provider=prov))
        masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "***"
        logger.debug(f"[CredentialPool] Added key {masked} for provider '{prov}'")

    def is_model_available(self, model: str, provider: Optional[str] = None) -> bool:
        """Check if at least one key in the pool is available for the specified model."""
        if provider:
            keys = self._pools.get(provider.lower(), [])
            return any(k.is_model_available(model) for k in keys) if keys else True
        for keys in self._pools.values():
            if any(k.is_model_available(model) for k in keys):
                return True
        return True

    def get_key(self, provider: str, model: Optional[str] = None, is_hot_path: bool = False) -> Optional[str]:
        """
        Get the most suitable available key for a provider.
        Prefers available keys with least recent usage (LRU round-robin).
        If model is specified, filters out keys with active cooldown for that specific model.
        If is_hot_path is True and all keys are in cooldown, returns None immediately without waiting.
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
                logger.warning(
                    f"[CredentialPool] All keys for '{prov}' (model={model}) in cooldown. "
                    f"Earliest ready in {max(0.0, earliest.cooldown_until - time.time()):.1f}s. "
                    f"{'Hot-path active: returning None for zero-downtime failover.' if is_hot_path else ''}"
                )
            return None

        # Sort by last_used ascending (LRU)
        selected = min(available, key=lambda x: x.last_used)
        selected.last_used = time.time()
        selected.total_requests += 1
        return selected.key

    def report_success(self, provider: str, key: str) -> None:
        """Report successful request for a key."""
        prov = provider.lower()
        for kh in self._pools.get(prov, []):
            if kh.key == key:
                kh.consecutive_errors = 0
                return

    def report_rate_limit(
        self,
        provider: str,
        key: str,
        cooldown_seconds: float = 60.0,
        model: Optional[str] = None,
        retry_after: Optional[float] = None,
        reset_at: Optional[float] = None,
    ) -> None:
        """Report a 429 rate limit and put key (or specific model) into temporary cooldown.
        
        Supports upstream header hints (retry_after or reset_at).
        """
        if retry_after is not None and retry_after > 0:
            effective_cd = float(retry_after)
        elif reset_at is not None:
            effective_cd = max(1.0, float(reset_at) - time.time())
        else:
            effective_cd = float(cooldown_seconds)

        prov = provider.lower()
        for kh in self._pools.get(prov, []):
            if kh.key == key:
                if model:
                    kh.model_cooldowns[model] = time.time() + effective_cd
                    kh.consecutive_errors += 1
                    kh.total_errors += 1
                    logger.warning(
                        f"[CredentialPool] Model '{model}' on key for '{prov}' rate limited. "
                        f"Cooldown set for {effective_cd:.1f}s"
                    )
                else:
                    kh.cooldown_until = time.time() + effective_cd
                    kh.consecutive_errors += 1
                    kh.total_errors += 1
                    logger.warning(
                        f"[CredentialPool] Key for '{prov}' rate limited. "
                        f"Cooldown set for {effective_cd:.1f}s"
                    )
                return

    def report_failure(self, provider: str, key: str, is_permanent: bool = False, reason: str = "") -> None:
        """Report a key failure (e.g. 401 invalid key or transient error)."""
        prov = provider.lower()
        for kh in self._pools.get(prov, []):
            if kh.key == key:
                kh.consecutive_errors += 1
                kh.total_errors += 1
                if is_permanent:
                    kh.is_active = False
                    kh.disabled_reason = reason or "Permanent credential failure"
                    logger.error(f"[CredentialPool] Permanently disabled key for '{prov}': {kh.disabled_reason}")
                elif kh.consecutive_errors >= 5:
                    # 5 consecutive transient errors trigger cooldown
                    kh.cooldown_until = time.time() + 120.0
                    logger.warning(f"[CredentialPool] Key for '{prov}' hit 5 consecutive errors. 120s cooldown.")
                return

    def get_pool_status(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Return diagnostic metrics of keys in the pool."""
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
                    "total_requests": kh.total_requests,
                    "total_errors": kh.total_errors,
                    "disabled_reason": kh.disabled_reason,
                })
            result[p] = entries
        return result


# Backward-compatibility alias
CredentialPool = APICredentialPool

_GLOBAL_CREDENTIAL_POOL: Optional[APICredentialPool] = None


def get_credential_pool() -> APICredentialPool:
    """Get singleton APICredentialPool instance."""
    global _GLOBAL_CREDENTIAL_POOL
    if _GLOBAL_CREDENTIAL_POOL is None:
        _GLOBAL_CREDENTIAL_POOL = APICredentialPool()
    return _GLOBAL_CREDENTIAL_POOL
