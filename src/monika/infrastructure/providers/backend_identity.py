# ==============================================================================
# File: analysis/providers/backend_identity.py
# ==============================================================================

"""
Backend Identity & Failure Scope Routing for Fast-Skip Failover Chains.
Institutional-grade LLM provider orchestration architecture.

Classifies failure blast radiuses into MODEL, CREDENTIAL, and ENDPOINT scopes.
When a credential or endpoint fails definitively (e.g. 401 Unauthorized or 402 Insufficient Quota),
subsequent candidate models sharing that credential/endpoint are immediately skipped,
preventing wasted latency and redundant failures.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Providers.BackendIdentity")


class FailureScope(str, Enum):
    MODEL = "model"            # Issue specific to this model name (e.g. 404 Model Not Found)
    CREDENTIAL = "credential"  # Issue invalidates the API key (e.g. 401 Invalid Key, 402 Billing)
    ENDPOINT = "endpoint"      # Issue invalidates the entire base URL (e.g. 503 DNS / Host unreachable)


@dataclass(frozen=True)
class BackendIdentity:
    provider: str
    model_name: str
    credential_hash: str = ""
    endpoint_url: str = ""

    @classmethod
    def create(
        cls,
        provider: str,
        model_name: str,
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ) -> BackendIdentity:
        c_hash = ""
        if api_key:
            c_hash = hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()[:16]
        return cls(
            provider=provider.strip().lower(),
            model_name=model_name.strip(),
            credential_hash=c_hash,
            endpoint_url=(endpoint_url or "").strip().lower(),
        )


class FailoverCandidateSkipper:
    """
    Maintains a temporal registry of failed scopes to skip futile retry candidates.
    TTL defaults to 300 seconds (5 minutes) for credential/endpoint blackouts.
    """

    def __init__(self, ttl_seconds: float = 300.0):
        self.ttl_seconds = ttl_seconds
        self._failed_models: Dict[str, float] = {}       # model_key -> expiry_time
        self._failed_credentials: Dict[str, float] = {}  # cred_hash -> expiry_time
        self._failed_endpoints: Dict[str, float] = {}    # endpoint_url -> expiry_time

    def _clean_expired(self) -> None:
        now = time.time()
        self._failed_models = {k: v for k, v in self._failed_models.items() if v > now}
        self._failed_credentials = {k: v for k, v in self._failed_credentials.items() if v > now}
        self._failed_endpoints = {k: v for k, v in self._failed_endpoints.items() if v > now}

    def record_failure(self, identity: BackendIdentity, scope: FailureScope) -> None:
        """Records a failure at the designated failure scope."""
        expiry = time.time() + self.ttl_seconds

        if scope == FailureScope.MODEL:
            m_key = f"{identity.provider}::{identity.model_name}"
            self._failed_models[m_key] = expiry
            logger.info(f"[CandidateSkipper] Blacklisted MODEL scope: '{m_key}' for {self.ttl_seconds}s")

        elif scope == FailureScope.CREDENTIAL:
            if identity.credential_hash:
                self._failed_credentials[identity.credential_hash] = expiry
                logger.warning(
                    f"[CandidateSkipper] Blacklisted CREDENTIAL scope for provider '{identity.provider}' "
                    f"(hash {identity.credential_hash}) for {self.ttl_seconds}s"
                )

        elif scope == FailureScope.ENDPOINT:
            if identity.endpoint_url:
                self._failed_endpoints[identity.endpoint_url] = expiry
                logger.warning(
                    f"[CandidateSkipper] Blacklisted ENDPOINT scope: '{identity.endpoint_url}' for {self.ttl_seconds}s"
                )

    def should_skip(self, identity: BackendIdentity) -> Tuple[bool, str]:
        """
        Determines whether a failover candidate should be skipped.
        Returns (should_skip: bool, reason: str).
        """
        self._clean_expired()

        # Check endpoint scope
        if identity.endpoint_url and identity.endpoint_url in self._failed_endpoints:
            return True, f"Endpoint '{identity.endpoint_url}' is in temporary blackout."

        # Check credential scope
        if identity.credential_hash and identity.credential_hash in self._failed_credentials:
            return True, f"Credential for provider '{identity.provider}' is in blackout (billing/auth failure)."

        # Check model scope
        m_key = f"{identity.provider}::{identity.model_name}"
        if m_key in self._failed_models:
            return True, f"Model '{m_key}' is in temporary blackout."

        return False, ""

    def clear(self) -> None:
        self._failed_models.clear()
        self._failed_credentials.clear()
        self._failed_endpoints.clear()
