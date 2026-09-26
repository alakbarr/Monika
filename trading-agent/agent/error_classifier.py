# ==============================================================================
# File: agent/error_classifier.py
# ==============================================================================

"""
Comprehensive Error Classifier & Recovery Directive Taxonomy.
Institutional-grade error classification for hybrid quant-LLM agent operations.

Categorizes raw API, network, context, and broker exceptions into structured
reasons with deterministic recovery hints (retry, compress, rotate credential,
fallback model, or quarantine trading symbol).
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger("TradingAgent.Agent.ErrorClassifier")


class FailoverReason(str, enum.Enum):
    """Structured taxonomy of failure reasons across LLM, infra, and broker layers."""
    # Auth & Permissions
    AUTH = "auth"
    AUTH_PERMANENT = "auth_permanent"
    BILLING = "billing"
    BILLING_UNVERIFIED = "billing_unverified"
    MODEL_ENTITLEMENT = "model_entitlement"

    # Rate Limiting & Capacity
    RATE_LIMIT = "rate_limit"
    UPSTREAM_RATE_LIMIT = "upstream_rate_limit"
    UPSTREAM_BLOCKED = "upstream_blocked"  # WAF, Cloudflare, 403 CDN
    OVERLOADED = "overloaded"

    # Network & Transport
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    SSL_CERT_VERIFICATION = "ssl_cert_verification"
    CONNECTION_LOST = "connection_lost"

    # Context & Payload
    CONTEXT_OVERFLOW = "context_overflow"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    IMAGE_TOO_LARGE = "image_too_large"
    IMAGE_CORRUPT = "image_corrupt"

    # Model & Formatting
    MODEL_NOT_FOUND = "model_not_found"
    PROVIDER_POLICY_BLOCKED = "provider_policy_blocked"
    CONTENT_POLICY_BLOCKED = "content_policy_blocked"
    FORMAT_ERROR = "format_error"
    ROLE_ALTERNATION = "role_alternation"
    INVALID_ENCRYPTED_CONTENT = "invalid_encrypted_content"
    MULTIMODAL_TOOL_CONTENT_UNSUPPORTED = "multimodal_tool_content_unsupported"
    REASONING_MANDATORY = "reasoning_mandatory"
    THINKING_SIGNATURE = "thinking_signature"
    LONG_CONTEXT_TIER = "long_context_tier"
    OAUTH_LONG_CONTEXT_BETA_FORBIDDEN = "oauth_long_context_beta_forbidden"
    LLAMA_CPP_GRAMMAR_PATTERN = "llama_cpp_grammar_pattern"

    # Trading & Financial Domain Sub-Taxonomy
    BROKER_DISCONNECTED = "broker_disconnected"
    MARGIN_CALL_RISK = "margin_call_risk"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    OFF_QUOTES = "off_quotes"
    MARKET_CLOSED = "market_closed"
    PRICE_SLIPPAGE_EXCEEDED = "price_slippage_exceeded"
    MARKET_DATA_STALE = "market_data_stale"

    # Fallback
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    """Represents a categorized failure with concrete action directives."""
    reason: FailoverReason
    status_code: Optional[int] = None
    error_code: Optional[str] = None
    message: str = ""
    retryable: bool = False
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False
    should_quarantine_symbol: bool = False
    cooldown_seconds: Optional[int] = None
    raw_exception: Optional[Exception] = None


# Regex patterns for matching common error strings
_CONTEXT_OVERFLOW_PATTERNS = [
    re.compile(r"context_length_exceeded", re.IGNORECASE),
    re.compile(r"maximum context length", re.IGNORECASE),
    re.compile(r"prompt is too long", re.IGNORECASE),
    re.compile(r"too many tokens", re.IGNORECASE),
    re.compile(r"exceeds the context window", re.IGNORECASE),
    re.compile(r"request exceeds the token limit", re.IGNORECASE),
]

_RATE_LIMIT_PATTERNS = [
    re.compile(r"rate_limit_exceeded", re.IGNORECASE),
    re.compile(r"too many requests", re.IGNORECASE),
    re.compile(r"quota exceeded", re.IGNORECASE),
    re.compile(r"resource has been exhausted", re.IGNORECASE),
    re.compile(r"requests per minute", re.IGNORECASE),
    re.compile(r"tokens per minute", re.IGNORECASE),
]

_BILLING_PATTERNS = [
    re.compile(r"billing", re.IGNORECASE),
    re.compile(r"insufficient_quota", re.IGNORECASE),
    re.compile(r"credit balance is too low", re.IGNORECASE),
    re.compile(r"out of credits", re.IGNORECASE),
    re.compile(r"payment required", re.IGNORECASE),
]

_ROLE_ALTERNATION_PATTERNS = [
    re.compile(r"conversation roles must alternate", re.IGNORECASE),
    re.compile(r"roles must alternate", re.IGNORECASE),
    re.compile(r"consecutive user messages", re.IGNORECASE),
    re.compile(r"expected role assistant", re.IGNORECASE),
    re.compile(r"expected role user", re.IGNORECASE),
]

_THINKING_SIGNATURE_PATTERNS = [
    re.compile(r"thoughtSignature", re.IGNORECASE),
    re.compile(r"thinking_signature", re.IGNORECASE),
    re.compile(r"missing thinking block", re.IGNORECASE),
    re.compile(r"thought block signature invalid", re.IGNORECASE),
]

_BROKER_DISCONNECT_PATTERNS = [
    re.compile(r"IPC disconnected", re.IGNORECASE),
    re.compile(r"terminal not connected", re.IGNORECASE),
    re.compile(r"MT5 terminal dead", re.IGNORECASE),
    re.compile(r"connection to broker lost", re.IGNORECASE),
    re.compile(r"socket closed by server", re.IGNORECASE),
]


def classify_api_error(
    exc: Exception,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> ClassifiedError:
    """
    Parses any exception and maps it to a canonical ClassifiedError.
    """
    if exc is None:
        return ClassifiedError(reason=FailoverReason.UNKNOWN)

    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    err_body = str(exc)
    err_code = getattr(exc, "code", None) or getattr(exc, "error_code", None)

    # 1. Trading & Broker Errors
    for pat in _BROKER_DISCONNECT_PATTERNS:
        if pat.search(err_body):
            return ClassifiedError(
                reason=FailoverReason.BROKER_DISCONNECTED,
                message=err_body,
                retryable=True,
                should_fallback=False,
                raw_exception=exc,
            )

    if "margin" in err_body.lower() and ("insufficient" in err_body.lower() or "not enough" in err_body.lower()):
        return ClassifiedError(
            reason=FailoverReason.INSUFFICIENT_MARGIN,
            message=err_body,
            retryable=False,
            should_quarantine_symbol=True,
            raw_exception=exc,
        )

    if "off quotes" in err_body.lower():
        return ClassifiedError(
            reason=FailoverReason.OFF_QUOTES,
            message=err_body,
            retryable=True,
            cooldown_seconds=15,
            should_quarantine_symbol=True,
            raw_exception=exc,
        )

    if "market closed" in err_body.lower():
        return ClassifiedError(
            reason=FailoverReason.MARKET_CLOSED,
            message=err_body,
            retryable=False,
            should_quarantine_symbol=True,
            raw_exception=exc,
        )

    # 2. Context Overflow
    for pat in _CONTEXT_OVERFLOW_PATTERNS:
        if pat.search(err_body):
            return ClassifiedError(
                reason=FailoverReason.CONTEXT_OVERFLOW,
                status_code=status_code or 400,
                message=err_body,
                retryable=True,
                should_compress=True,
                should_fallback=False,
                raw_exception=exc,
            )

    # 3. Thinking Signature / Gemini Replay
    for pat in _THINKING_SIGNATURE_PATTERNS:
        if pat.search(err_body):
            return ClassifiedError(
                reason=FailoverReason.THINKING_SIGNATURE,
                status_code=status_code or 400,
                message=err_body,
                retryable=True,
                should_compress=False,
                raw_exception=exc,
            )

    # 4. Role Alternation
    for pat in _ROLE_ALTERNATION_PATTERNS:
        if pat.search(err_body):
            return ClassifiedError(
                reason=FailoverReason.ROLE_ALTERNATION,
                status_code=status_code or 400,
                message=err_body,
                retryable=True,
                should_compress=False,
                raw_exception=exc,
            )

    # 5. Billing & Quota
    for pat in _BILLING_PATTERNS:
        if pat.search(err_body):
            return ClassifiedError(
                reason=FailoverReason.BILLING,
                status_code=status_code or 402,
                message=err_body,
                retryable=False,
                should_rotate_credential=True,
                should_fallback=True,
                raw_exception=exc,
            )

    # 6. Rate Limit (429)
    if status_code == 429:
        return ClassifiedError(
            reason=FailoverReason.RATE_LIMIT,
            status_code=429,
            message=err_body,
            retryable=True,
            should_rotate_credential=True,
            should_fallback=True,
            raw_exception=exc,
        )

    for pat in _RATE_LIMIT_PATTERNS:
        if pat.search(err_body):
            return ClassifiedError(
                reason=FailoverReason.RATE_LIMIT,
                status_code=429,
                message=err_body,
                retryable=True,
                should_rotate_credential=True,
                should_fallback=True,
                raw_exception=exc,
            )

    # 7. Auth & Forbidden (401 / 403)
    if status_code in (401, 403):
        if "cloudflare" in err_body.lower() or "waf" in err_body.lower() or "blocked" in err_body.lower():
            return ClassifiedError(
                reason=FailoverReason.UPSTREAM_BLOCKED,
                status_code=status_code,
                message=err_body,
                retryable=True,
                should_fallback=True,
                raw_exception=exc,
            )
        return ClassifiedError(
            reason=FailoverReason.AUTH_PERMANENT,
            status_code=status_code,
            message=err_body,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
            raw_exception=exc,
        )

    # 8. Timeout
    if isinstance(exc, (TimeoutError, TimeoutException := getattr(__import__("asyncio"), "TimeoutError", TimeoutError))):
        return ClassifiedError(
            reason=FailoverReason.TIMEOUT,
            message=err_body or "Request timed out",
            retryable=True,
            should_fallback=True,
            raw_exception=exc,
        )

    if "timeout" in err_body.lower() or "timed out" in err_body.lower():
        return ClassifiedError(
            reason=FailoverReason.TIMEOUT,
            message=err_body,
            retryable=True,
            should_fallback=True,
            raw_exception=exc,
        )

    # 9. Server Overload / 5xx
    if status_code in (500, 502, 503, 504, 529):
        return ClassifiedError(
            reason=FailoverReason.OVERLOADED if status_code == 529 else FailoverReason.SERVER_ERROR,
            status_code=status_code,
            message=err_body,
            retryable=True,
            should_fallback=True,
            raw_exception=exc,
        )

    # 10. SSL Certificate
    if "ssl" in err_body.lower() and ("cert" in err_body.lower() or "verify" in err_body.lower()):
        return ClassifiedError(
            reason=FailoverReason.SSL_CERT_VERIFICATION,
            message=err_body,
            retryable=False,
            should_fallback=True,
            raw_exception=exc,
        )

    # Default Fallback
    return ClassifiedError(
        reason=FailoverReason.UNKNOWN,
        status_code=status_code,
        message=err_body,
        retryable=False,
        should_fallback=False,
        raw_exception=exc,
    )
