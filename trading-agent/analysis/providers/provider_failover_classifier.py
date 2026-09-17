"""
Structured Error Classification Pipeline.

Maps raw provider exceptions into actionable FailoverReasons.
Each reason carries:
  - should_failover: whether to try next model or recover in-place
  - should_compress: whether to compact context instead of failover
  - backoff_seconds: recommended wait before retry
  - max_retries: max same-model retries for this error class
"""
from enum import Enum
from typing import Tuple
import logging
import re

logger = logging.getLogger("TradingAgent.ErrorClassifier")


class FailoverReason(str, Enum):
    AUTH_TRANSIENT = "auth_transient"
    AUTH_PERMANENT = "auth_permanent"
    BILLING_EXHAUSTED = "billing"
    RATE_LIMIT_API = "rate_limit_api"
    RATE_LIMIT_MODEL = "rate_limit_model"
    UPSTREAM_RATE_LIMIT = "upstream_rate_limit"
    CONTEXT_OVERFLOW = "context_overflow"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    MODEL_OVERLOADED = "overloaded"
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_UNAVAILABLE = "unavailable"
    INVALID_REQUEST = "invalid_request"
    NETWORK_TIMEOUT = "timeout"
    NETWORK_CONNECTION = "connection"
    CONTENT_FILTERED = "content_filtered"
    SERVER_ERROR = "server_error"
    BROKER_MARGIN_CALL = "broker_margin_call"
    SILENT_OVERFLOW = "silent_overflow"
    LENGTH_STOP_OVERFLOW = "length_stop_overflow"
    UNKNOWN = "unknown"

    @property
    def should_failover(self) -> bool:
        """Whether this error warrants trying a different model."""
        NO_FAILOVER = {
            FailoverReason.CONTEXT_OVERFLOW,
            FailoverReason.PAYLOAD_TOO_LARGE,
            FailoverReason.SILENT_OVERFLOW,
            FailoverReason.LENGTH_STOP_OVERFLOW,
            FailoverReason.RATE_LIMIT_API,
            FailoverReason.MODEL_OVERLOADED,
            FailoverReason.NETWORK_TIMEOUT,
            FailoverReason.NETWORK_CONNECTION,
            FailoverReason.CONTENT_FILTERED,
            FailoverReason.SERVER_ERROR,
            FailoverReason.INVALID_REQUEST,
            FailoverReason.BROKER_MARGIN_CALL,
        }
        return self not in NO_FAILOVER

    @property
    def should_compress(self) -> bool:
        """Whether to compact context instead of failover."""
        return self in {
            FailoverReason.CONTEXT_OVERFLOW,
            FailoverReason.PAYLOAD_TOO_LARGE,
            FailoverReason.SILENT_OVERFLOW,
            FailoverReason.LENGTH_STOP_OVERFLOW,
        }

    @property
    def backoff_seconds(self) -> float:
        _MAP = {
            FailoverReason.RATE_LIMIT_API: 15.0,
            FailoverReason.RATE_LIMIT_MODEL: 60.0,
            FailoverReason.UPSTREAM_RATE_LIMIT: 20.0,
            FailoverReason.MODEL_OVERLOADED: 10.0,
            FailoverReason.NETWORK_TIMEOUT: 5.0,
            FailoverReason.NETWORK_CONNECTION: 5.0,
            FailoverReason.SERVER_ERROR: 10.0,
            FailoverReason.CONTENT_FILTERED: 2.0,
            FailoverReason.INVALID_REQUEST: 0.0,
            FailoverReason.BROKER_MARGIN_CALL: 0.0,
            FailoverReason.SILENT_OVERFLOW: 0.0,
            FailoverReason.LENGTH_STOP_OVERFLOW: 0.0,
        }
        return _MAP.get(self, 0.0)

    @property
    def max_retries(self) -> int:
        _MAP = {
            FailoverReason.RATE_LIMIT_API: 3,
            FailoverReason.RATE_LIMIT_MODEL: 2,
            FailoverReason.UPSTREAM_RATE_LIMIT: 1,
            FailoverReason.MODEL_OVERLOADED: 3,
            FailoverReason.NETWORK_TIMEOUT: 2,
            FailoverReason.NETWORK_CONNECTION: 2,
            FailoverReason.CONTEXT_OVERFLOW: 1,
            FailoverReason.PAYLOAD_TOO_LARGE: 1,
            FailoverReason.SILENT_OVERFLOW: 1,
            FailoverReason.LENGTH_STOP_OVERFLOW: 1,
            FailoverReason.SERVER_ERROR: 2,
            FailoverReason.CONTENT_FILTERED: 1,
            FailoverReason.INVALID_REQUEST: 0,
            FailoverReason.BROKER_MARGIN_CALL: 0,
        }
        return _MAP.get(self, 0)


# Pre-compiled patterns for fast classification
_OVERFLOW_PATTERNS = re.compile(
    r"context.?length|maximum context|prompt.?is.?too.?long|token.?limit|"
    r"content.?too.?large|exceeds.?the.?model|exceeds.?the.?maximum.?number.?of.?tokens|"
    r"request.?too.?large|413|max_tokens_exceeded",
    re.IGNORECASE,
)
_AUTH_PATTERNS = re.compile(r"401|unauthorized|invalid.?api.?key|invalid.?x-api-key|authentication", re.IGNORECASE)
_BILLING_PATTERNS = re.compile(r"402|insufficient.?quota|billing|credit|payment.?required", re.IGNORECASE)
_UPSTREAM_RATE_PATTERNS = re.compile(r"upstream.?(?:429|rate|service|error)|openrouter.?(?:upstream|provider.?rate)", re.IGNORECASE)
_RATE_PATTERNS = re.compile(r"429|rate.?limit|too.?many.?requests|resource.?exhausted", re.IGNORECASE)
_MARGIN_PATTERNS = re.compile(r"margin.?call|insufficient.?margin|not.?enough.?money|no.?money", re.IGNORECASE)
_INVALID_REQ_PATTERNS = re.compile(r"400|bad.?request|invalid.?request|schema.?validation.?failed", re.IGNORECASE)
_NOT_FOUND_PATTERNS = re.compile(r"404|model.?not.?found|does.?not.?exist|not_found_error", re.IGNORECASE)
_OVERLOAD_PATTERNS = re.compile(r"overloaded|503|529|service.?unavailable|capacity", re.IGNORECASE)
_FILTER_PATTERNS = re.compile(r"content.?filter|content.?policy|safety|blocked|harmful", re.IGNORECASE)
_TIMEOUT_PATTERNS = re.compile(r"timeout|timed.?out|deadline.?exceeded", re.IGNORECASE)
_CONN_PATTERNS = re.compile(r"connection.?(?:refused|reset|error|closed)|broken.?pipe|eof", re.IGNORECASE)
_SERVER_PATTERNS = re.compile(r"500|502|internal.?server.?error|bad.?gateway", re.IGNORECASE)


def classify_error(error: Exception) -> Tuple[FailoverReason, str]:
    """
    Classify a provider exception into a structured FailoverReason.

    Returns:
        (reason, human_readable_detail)
    """
    msg = str(error)
    error_type = type(error).__name__

    # Order matters: check specific patterns before generic ones

    # 1. Context overflow (MUST check before generic 4xx)
    if _OVERFLOW_PATTERNS.search(msg):
        return FailoverReason.CONTEXT_OVERFLOW, "Context window exceeded"

    # 2. Broker margin call
    if _MARGIN_PATTERNS.search(msg):
        return FailoverReason.BROKER_MARGIN_CALL, "Broker margin call or insufficient margin"

    # 3. Auth
    if _AUTH_PATTERNS.search(msg):
        if re.search(r"expired|refresh|rotate", msg, re.IGNORECASE):
            return FailoverReason.AUTH_TRANSIENT, "Auth token expired — refreshable"
        return FailoverReason.AUTH_PERMANENT, "API key permanently invalid"

    # 4. Billing
    if _BILLING_PATTERNS.search(msg):
        return FailoverReason.BILLING_EXHAUSTED, "Credits/quota depleted"

    # 5. Upstream & Rate limit
    if _UPSTREAM_RATE_PATTERNS.search(msg):
        return FailoverReason.UPSTREAM_RATE_LIMIT, "Upstream provider rate limit"
    if _RATE_PATTERNS.search(msg):
        if re.search(r"retry.?after|model|provider", msg, re.IGNORECASE):
            return FailoverReason.RATE_LIMIT_MODEL, "Model-level rate limit"
        return FailoverReason.RATE_LIMIT_API, "API gateway rate limit"

    # 6. Invalid request / Schema failure
    if _INVALID_REQ_PATTERNS.search(msg):
        return FailoverReason.INVALID_REQUEST, f"Invalid request / schema validation failed: {error_type}"

    # 7. Model not found
    if _NOT_FOUND_PATTERNS.search(msg):
        return FailoverReason.MODEL_NOT_FOUND, f"Model not found: {error_type}"

    # 8. Overloaded
    if _OVERLOAD_PATTERNS.search(msg):
        return FailoverReason.MODEL_OVERLOADED, "Model overloaded — short backoff"

    # 9. Content filtered
    if _FILTER_PATTERNS.search(msg):
        return FailoverReason.CONTENT_FILTERED, "Content safety filter triggered"

    # 10. Timeout
    if _TIMEOUT_PATTERNS.search(msg) or "TimeoutError" in error_type:
        return FailoverReason.NETWORK_TIMEOUT, "Request timed out"

    # 11. Connection
    if _CONN_PATTERNS.search(msg) or "ConnectionError" in error_type:
        return FailoverReason.NETWORK_CONNECTION, "Network connection failed"

    # 12. Server error
    if _SERVER_PATTERNS.search(msg):
        return FailoverReason.SERVER_ERROR, "Provider server error"

    return FailoverReason.UNKNOWN, f"Unclassified {error_type}: {msg[:120]}"
