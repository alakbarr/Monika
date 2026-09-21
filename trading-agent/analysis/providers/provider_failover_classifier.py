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
    OUTPUT_CAP_REACHED = "output_cap_reached"
    COMPLETION_CEILING_EXCEEDED = "completion_ceiling_exceeded"
    HARD_QUOTA_EXHAUSTED = "hard_quota_exhausted"
    TRANSIENT_RATE_LIMIT = "transient_rate_limit"
    UPSTREAM_BLOCKED = "upstream_blocked"
    IMAGE_TOO_LARGE = "image_too_large"
    IMAGE_CORRUPT = "image_corrupt"
    ROLE_ALTERNATION = "role_alternation"
    THINKING_SIGNATURE = "thinking_signature"
    MODEL_ENTITLEMENT = "model_entitlement"
    UNKNOWN = "unknown"

    @property
    def should_failover(self) -> bool:
        """Whether this error warrants trying a different model."""
        NO_FAILOVER = {
            FailoverReason.CONTEXT_OVERFLOW,
            FailoverReason.PAYLOAD_TOO_LARGE,
            FailoverReason.SILENT_OVERFLOW,
            FailoverReason.LENGTH_STOP_OVERFLOW,
            FailoverReason.OUTPUT_CAP_REACHED,
            FailoverReason.COMPLETION_CEILING_EXCEEDED,
            FailoverReason.RATE_LIMIT_API,
            FailoverReason.TRANSIENT_RATE_LIMIT,
            FailoverReason.MODEL_OVERLOADED,
            FailoverReason.NETWORK_TIMEOUT,
            FailoverReason.NETWORK_CONNECTION,
            FailoverReason.CONTENT_FILTERED,
            FailoverReason.SERVER_ERROR,
            FailoverReason.INVALID_REQUEST,
            FailoverReason.BROKER_MARGIN_CALL,
            FailoverReason.IMAGE_TOO_LARGE,
            FailoverReason.ROLE_ALTERNATION,
        }
        return self not in NO_FAILOVER

    def can_failover(self, is_hot_path: bool = False) -> bool:
        """Whether this error warrants trying a different model, accounting for hot-path zero-downtime urgency."""
        if is_hot_path and self in (
            FailoverReason.RATE_LIMIT_API,
            FailoverReason.RATE_LIMIT_MODEL,
            FailoverReason.TRANSIENT_RATE_LIMIT,
            FailoverReason.UPSTREAM_RATE_LIMIT,
            FailoverReason.MODEL_OVERLOADED,
            FailoverReason.UPSTREAM_BLOCKED,
            FailoverReason.MODEL_ENTITLEMENT,
            FailoverReason.THINKING_SIGNATURE,
        ):
            return True
        return self.should_failover

    @property
    def should_compress(self) -> bool:
        """Whether to compact context instead of failover."""
        return self in {
            FailoverReason.CONTEXT_OVERFLOW,
            FailoverReason.PAYLOAD_TOO_LARGE,
            FailoverReason.SILENT_OVERFLOW,
            FailoverReason.LENGTH_STOP_OVERFLOW,
            FailoverReason.IMAGE_TOO_LARGE,
        }

    @property
    def is_output_cap(self) -> bool:
        return self in (FailoverReason.OUTPUT_CAP_REACHED, FailoverReason.LENGTH_STOP_OVERFLOW)

    @property
    def is_completion_ceiling(self) -> bool:
        return self == FailoverReason.COMPLETION_CEILING_EXCEEDED

    @property
    def is_hard_quota_exhausted(self) -> bool:
        return self in (FailoverReason.HARD_QUOTA_EXHAUSTED, FailoverReason.BILLING_EXHAUSTED)

    @property
    def backoff_seconds(self) -> float:
        _MAP = {
            FailoverReason.RATE_LIMIT_API: 15.0,
            FailoverReason.RATE_LIMIT_MODEL: 60.0,
            FailoverReason.TRANSIENT_RATE_LIMIT: 15.0,
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
            FailoverReason.OUTPUT_CAP_REACHED: 0.0,
            FailoverReason.COMPLETION_CEILING_EXCEEDED: 0.0,
            FailoverReason.HARD_QUOTA_EXHAUSTED: 0.0,
            FailoverReason.BILLING_EXHAUSTED: 0.0,
            FailoverReason.UPSTREAM_BLOCKED: 30.0,
            FailoverReason.IMAGE_TOO_LARGE: 0.0,
            FailoverReason.IMAGE_CORRUPT: 0.0,
            FailoverReason.ROLE_ALTERNATION: 0.0,
            FailoverReason.THINKING_SIGNATURE: 0.0,
            FailoverReason.MODEL_ENTITLEMENT: 0.0,
        }
        return _MAP.get(self, 0.0)

    @property
    def max_retries(self) -> int:
        _MAP = {
            FailoverReason.RATE_LIMIT_API: 3,
            FailoverReason.RATE_LIMIT_MODEL: 2,
            FailoverReason.TRANSIENT_RATE_LIMIT: 3,
            FailoverReason.UPSTREAM_RATE_LIMIT: 1,
            FailoverReason.MODEL_OVERLOADED: 3,
            FailoverReason.NETWORK_TIMEOUT: 2,
            FailoverReason.NETWORK_CONNECTION: 2,
            FailoverReason.CONTEXT_OVERFLOW: 1,
            FailoverReason.PAYLOAD_TOO_LARGE: 1,
            FailoverReason.SILENT_OVERFLOW: 1,
            FailoverReason.LENGTH_STOP_OVERFLOW: 0,
            FailoverReason.OUTPUT_CAP_REACHED: 0,
            FailoverReason.COMPLETION_CEILING_EXCEEDED: 1,
            FailoverReason.HARD_QUOTA_EXHAUSTED: 0,
            FailoverReason.BILLING_EXHAUSTED: 0,
            FailoverReason.SERVER_ERROR: 2,
            FailoverReason.CONTENT_FILTERED: 1,
            FailoverReason.INVALID_REQUEST: 0,
            FailoverReason.BROKER_MARGIN_CALL: 0,
            FailoverReason.UPSTREAM_BLOCKED: 1,
            FailoverReason.IMAGE_TOO_LARGE: 1,
            FailoverReason.IMAGE_CORRUPT: 0,
            FailoverReason.ROLE_ALTERNATION: 1,
            FailoverReason.THINKING_SIGNATURE: 0,
            FailoverReason.MODEL_ENTITLEMENT: 0,
        }
        return _MAP.get(self, 0)


# Pre-compiled patterns for fast classification
_COMPLETION_CEILING_PATTERNS = re.compile(
    r"max_(?:completion_)?tokens.?is.?too.?large|"
    r"completion.?tokens.?exceed|"
    r"maximum.?completion.?tokens|"
    r"max_(?:completion_)?tokens.?cannot.?exceed|"
    r"cannot.?be.?greater.?than.*max_(?:completion_)?tokens|"
    r"max_(?:completion_)?tokens.*(?:must be |cannot be )?(?:less than or equal to|<=|greater than|exceeds|too large)|"
    r"(?:must be |cannot be )?(?:less than or equal to|<=).*max_(?:completion_)?tokens|"
    r"max_completion_tokens.?exceeded|"
    r"max_(?:completion_)?tokens\s*:\s*\d+\s*>\s*\d+",
    re.IGNORECASE,
)
_HARD_QUOTA_PATTERNS = re.compile(
    r"insufficient_quota|"
    r"exceeded.?your.?current.?quota|"
    r"quota.?exceeded|"
    r"credit.?balance.?is.?too.?low|"
    r"account.?has.?run.?out.?of.?credits|"
    r"monthly.?quota.?reached|"
    r"check.?your.?plan.?and.?billing",
    re.IGNORECASE,
)
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
_WAF_PATTERNS = re.compile(r"cloudflare|just\s+a\s+moment|access\s+denied|cf-ray|blocked\s+by\s+waf|403\s+forbidden", re.IGNORECASE)
_ROLE_ALT_PATTERNS = re.compile(r"role\s+alternation|consecutive\s+(?:user|assistant)|messages\s+must\s+alternate", re.IGNORECASE)
_THINKING_PATTERNS = re.compile(r"thinking\s+signature|thought\s+signature|invalid\s+thought", re.IGNORECASE)
_ENTITLEMENT_PATTERNS = re.compile(r"not\s+entitled|does\s+not\s+have\s+access|permission\s+denied|tier\s+required", re.IGNORECASE)
_IMAGE_LARGE_PATTERNS = re.compile(r"image\s+too\s+large|maximum\s+image\s+size|exceeds\s+image\s+limit", re.IGNORECASE)
_IMAGE_CORRUPT_PATTERNS = re.compile(r"cannot\s+decode\s+image|invalid\s+image\s+data|unsupported\s+image", re.IGNORECASE)


def extract_completion_ceiling(error: Exception | str) -> int | None:
    """
    Extract allowed completion token ceiling from provider error message.
    e.g. 'max_tokens is too large: 32000 > 8192' -> 8192
    'max_tokens must be less than or equal to 4096' -> 4096
    """
    msg = str(error)
    # Pattern: 32000 > 8192
    m = re.search(r"\d+\s*>\s*(\d+)", msg)
    if m:
        try:
            return int(m.group(1))
        except (ValueError, IndexError):
            pass
    # Pattern: less than or equal to 8192 / cannot exceed 8192 / max 8192
    m = re.search(r"(?:less than or equal to|cannot exceed|maximum allowed is|limit is|must be <=)\s*[`'\"]?(\d+)", msg, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except (ValueError, IndexError):
            pass
    return None


def classify_error(error: Exception) -> Tuple[FailoverReason, str]:
    """
    Classify a provider exception into a structured FailoverReason.

    Returns:
        (reason, human_readable_detail)
    """
    msg = str(error)
    error_type = type(error).__name__

    # Order matters: check specific patterns before generic ones

    # 0. Completion ceiling limit (MUST check before generic overflow / 400)
    if _COMPLETION_CEILING_PATTERNS.search(msg):
        return FailoverReason.COMPLETION_CEILING_EXCEEDED, "Completion token limit exceeded model maximum"

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

    # 4. Hard Quota & Billing
    if _HARD_QUOTA_PATTERNS.search(msg):
        return FailoverReason.HARD_QUOTA_EXHAUSTED, "Hard quota / credits depleted for provider"
    if _BILLING_PATTERNS.search(msg):
        return FailoverReason.BILLING_EXHAUSTED, "Credits/quota depleted"

    # 5. Upstream & Rate limit
    if _UPSTREAM_RATE_PATTERNS.search(msg):
        return FailoverReason.UPSTREAM_RATE_LIMIT, "Upstream provider rate limit"
    if _RATE_PATTERNS.search(msg):
        if re.search(r"retry.?after|model|provider", msg, re.IGNORECASE):
            return FailoverReason.RATE_LIMIT_MODEL, "Model-level rate limit"
        if re.search(r"requests.?per.?minute|tokens.?per.?minute|RPM|TPM", msg, re.IGNORECASE):
            return FailoverReason.TRANSIENT_RATE_LIMIT, "Transient rate limit (RPM/TPM)"
        return FailoverReason.RATE_LIMIT_API, "API gateway rate limit"

    # 6. WAF / Cloudflare blockage (must check before generic filter or 403)
    if _WAF_PATTERNS.search(msg):
        return FailoverReason.UPSTREAM_BLOCKED, "Upstream WAF / Cloudflare block (403)"

    # 7. Specific payload issues before generic 400
    if _IMAGE_LARGE_PATTERNS.search(msg):
        return FailoverReason.IMAGE_TOO_LARGE, "Attached chart image exceeds model size limits"
    if _IMAGE_CORRUPT_PATTERNS.search(msg):
        return FailoverReason.IMAGE_CORRUPT, "Attached chart image corrupt or undecodable"
    if _ROLE_ALT_PATTERNS.search(msg):
        return FailoverReason.ROLE_ALTERNATION, "Provider rejected turn due to consecutive same-role messages"
    if _THINKING_PATTERNS.search(msg):
        return FailoverReason.THINKING_SIGNATURE, "Provider failed reasoning/thinking signature validation"
    if _ENTITLEMENT_PATTERNS.search(msg):
        return FailoverReason.MODEL_ENTITLEMENT, "Account lacks access or entitlement for model"

    # 8. Invalid request / Schema failure
    if _INVALID_REQ_PATTERNS.search(msg):
        return FailoverReason.INVALID_REQUEST, f"Invalid request / schema validation failed: {error_type}"

    # 9. Model not found
    if _NOT_FOUND_PATTERNS.search(msg):
        return FailoverReason.MODEL_NOT_FOUND, f"Model not found: {error_type}"

    # 10. Overloaded
    if _OVERLOAD_PATTERNS.search(msg):
        return FailoverReason.MODEL_OVERLOADED, "Model overloaded — short backoff"

    # 11. Content filtered
    if _FILTER_PATTERNS.search(msg):
        return FailoverReason.CONTENT_FILTERED, "Content safety filter triggered"

    # 12. Timeout
    if _TIMEOUT_PATTERNS.search(msg) or "TimeoutError" in error_type:
        return FailoverReason.NETWORK_TIMEOUT, "Request timed out"

    # 13. Connection
    if _CONN_PATTERNS.search(msg) or "ConnectionError" in error_type:
        return FailoverReason.NETWORK_CONNECTION, "Network connection failed"

    # 14. Server error
    if _SERVER_PATTERNS.search(msg):
        return FailoverReason.SERVER_ERROR, "Provider server error"

    return FailoverReason.UNKNOWN, f"Unclassified {error_type}: {msg[:120]}"
