# ==============================================================================
# File: infrastructure/providers/circuit_breaker.py
# ==============================================================================

"""
Provider Circuit Breaker & Endpoint Blackhole Cache.
Prevents cascade failures across AI providers and local endpoint timeouts.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.LLMFactory")


logger = logging.getLogger("TradingAgent.LLMFactory")

# Memoized routes that reject native response_format / json_schema
_UNSUPPORTED_SCHEMA_ROUTES: set[tuple[str, str]] = set()

# Trading hot-path roles requiring zero-downtime eager failover
HOT_PATH_ROLES: set[str] = {
    "debate",
    "debate_judge",
    "debate_bull",
    "debate_bear",
    "bull_debater",
    "bear_debater",
    "bull_analyst",
    "bear_analyst",
    "macro_bull",
    "macro_bear",
    "macro_judge",
    "judge",
    "investment_judge",
    "risk_gate",
    "risk_gate_aggressive",
    "risk_gate_conservative",
    "risk_gate_neutral",
    "aggressive_risk",
    "conservative_risk",
    "neutral_risk",
    "pre_commit_gate",
    "execution_verifier",
    "position_guardian",
    "jev_position_guard",
    "jev_trigger_validator",
    "trailing_stop",
    "trigger_evaluator",
    "reactive_graph",
    "alpha_synthesis",
    "signal_arbitrator",
}


class ProviderCircuitBreaker:
    """
    Tracks consecutive 5xx/timeouts and permanent entitlement errors across providers.
    States: CLOSED (normal), OPEN (cooldown after 3 failures), HALF_OPEN (1 canary probe).
    """

    _states: dict[str, str] = {}
    _consecutive_failures: dict[str, int] = {}
    _open_until: dict[str, float] = {}
    _blacklisted_models: dict[tuple[str, str], float] = {}
    _blacklist_reasons: dict[tuple[str, str], str] = {}

    FAILURE_THRESHOLD: int = 3
    COOLDOWN_SECONDS: float = 60.0

    @classmethod
    def is_provider_available(cls, provider: str, model: Optional[str] = None) -> bool:
        # Check provider-level circuit
        state = cls._states.get(provider, "CLOSED")
        if state == "OPEN":
            now = time.time()
            if now >= cls._open_until.get(provider, 0.0):
                cls._states[provider] = "HALF_OPEN"
                logger.info(
                    f"[CircuitBreaker] Provider '{provider}' transitioning OPEN -> HALF_OPEN (canary probe allowed)"
                )
                return True
            return False

        # If model is specified, check model-level circuit
        if model:
            key = f"{provider}:{model}"
            m_state = cls._states.get(key, "CLOSED")
            if m_state == "OPEN":
                now = time.time()
                if now >= cls._open_until.get(key, 0.0):
                    cls._states[key] = "HALF_OPEN"
                    logger.info(
                        f"[CircuitBreaker] Model '{key}' transitioning OPEN -> HALF_OPEN (canary probe allowed)"
                    )
                    return True
                return False

        return True

    @classmethod
    def record_provider_success(cls, provider: str, model: Optional[str] = None) -> None:
        if cls._consecutive_failures.get(provider, 0) > 0 or cls._states.get(provider) != "CLOSED":
            logger.info(f"[CircuitBreaker] Provider '{provider}' healthy. Circuit CLOSED.")
        cls._consecutive_failures[provider] = 0
        cls._states[provider] = "CLOSED"
        cls._open_until.pop(provider, None)

        if model:
            key = f"{provider}:{model}"
            if cls._consecutive_failures.get(key, 0) > 0 or cls._states.get(key) != "CLOSED":
                logger.info(f"[CircuitBreaker] Model '{key}' healthy. Circuit CLOSED.")
            cls._consecutive_failures[key] = 0
            cls._states[key] = "CLOSED"
            cls._open_until.pop(key, None)

    @classmethod
    def record_provider_failure(
        cls,
        provider: str,
        is_server_or_timeout: bool = True,
        reason: str = "",
        model: Optional[str] = None,
    ) -> None:
        if is_server_or_timeout:
            if model:
                key = f"{provider}:{model}"
                cnt = cls._consecutive_failures.get(key, 0) + 1
                cls._consecutive_failures[key] = cnt
                if cnt >= cls.FAILURE_THRESHOLD:
                    cls._states[key] = "OPEN"
                    cls._open_until[key] = time.time() + cls.COOLDOWN_SECONDS
                    logger.warning(
                        f"[CircuitBreaker] Model '{key}' circuit OPEN ({cnt} consecutive server/timeout errors). "
                        f"Cooldown for {cls.COOLDOWN_SECONDS:.0f}s. Reason: {reason}"
                    )
            else:
                cnt = cls._consecutive_failures.get(provider, 0) + 1
                cls._consecutive_failures[provider] = cnt
                if cnt >= cls.FAILURE_THRESHOLD:
                    cls._states[provider] = "OPEN"
                    cls._open_until[provider] = time.time() + cls.COOLDOWN_SECONDS
                    logger.warning(
                        f"[CircuitBreaker] Provider '{provider}' circuit OPEN ({cnt} consecutive server/timeout errors). "
                        f"Cooldown for {cls.COOLDOWN_SECONDS:.0f}s. Reason: {reason}"
                    )

    @classmethod
    def blacklist_model(cls, provider: str, model: str, reason: str, duration: float = 1800.0) -> None:
        key = (provider, model)
        cls._blacklisted_models[key] = time.time() + duration
        cls._blacklist_reasons[key] = reason
        logger.warning(
            f"[CapabilityBlacklist] Blacklisting model '{model}' ({provider}) for {duration:.0f}s. Reason: {reason}"
        )

    @classmethod
    def is_model_blacklisted(cls, provider: str, model: str) -> bool:
        key = (provider, model)
        if key in cls._blacklisted_models:
            if time.time() < cls._blacklisted_models[key]:
                return True
            cls._blacklisted_models.pop(key, None)
            cls._blacklist_reasons.pop(key, None)
        return False

    @classmethod
    def reset(cls) -> None:
        cls._states.clear()
        cls._consecutive_failures.clear()
        cls._open_until.clear()
        cls._blacklisted_models.clear()
        cls._blacklist_reasons.clear()


class EndpointBlackhole:
    """
    30-second blackhole cache for unresponsive local models (Ollama/vLLM) or hanging endpoints.
    Enables sub-100ms instant failover on subsequent turns without waiting for full network timeouts.
    """

    _blackhole: Dict[str, float] = {}

    @classmethod
    def is_blackholed(cls, endpoint_or_model: str) -> bool:
        expire_at = cls._blackhole.get(endpoint_or_model)
        if expire_at:
            if time.time() < expire_at:
                return True
            cls._blackhole.pop(endpoint_or_model, None)
        return False

    @classmethod
    def blackhole_endpoint(cls, endpoint_or_model: str, ttl_seconds: float = 30.0) -> None:
        cls._blackhole[endpoint_or_model] = time.time() + ttl_seconds
        logger.warning(
            f"[EndpointBlackhole] Blackholing '{endpoint_or_model}' for {ttl_seconds:.0f}s due to connection failure."
        )

    @classmethod
    def reset(cls) -> None:
        cls._blackhole.clear()
